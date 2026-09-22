"""
RAG-based Q&A service for codebases.

This module implements Retrieval-Augmented Generation (RAG) for answering
questions about codebases by:
1. Retrieving relevant code from Neo4j graph database
2. Constructing context from code, call graphs, and relationships
3. Generating answers using DeepSeek LLM
"""

import logging
from typing import List, Dict, Optional, Any

from app.services.llm.client import DeepSeekClient
from app.services.llm import prompts

logger = logging.getLogger(__name__)


class CodeQA:
    """
    RAG-based Q&A system for codebases.

    Uses graph database to find relevant code context and LLM to generate answers.
    """

    def __init__(
        self,
        client: Optional[DeepSeekClient] = None,
        neo4j_driver: Optional[Any] = None,
        embedder: Optional[Any] = None,
    ):
        """
        Initialize Q&A system.

        Args:
            client: DeepSeek client instance
            neo4j_driver: Neo4j driver for graph queries
            embedder: CodeEmbedder used to embed the question. Loaded lazily
                on first use when not supplied.
        """
        self.client = client or DeepSeekClient()
        self.neo4j_driver = neo4j_driver
        self.embedder = embedder

    def find_relevant_code(
        self,
        repo_id: str,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find code elements relevant to the query.

        Retrieval is by meaning first: the question is embedded and Neo4j's
        vector index returns the nearest code elements, then one graph hop
        pulls in each element's callers, callees and imports. The answer to a
        question about code usually lives in the caller or the callee, not in
        the chunk that matched.

        Falls back to keyword matching on names when no embeddings exist yet
        (a repository indexed before embeddings were added, or a Neo4j too old
        for vector indexes).

        Args:
            repo_id: Repository ID
            query: User query
            max_results: Maximum results to return

        Returns:
            List of relevant code elements with context
        """
        results = self._find_by_embedding(repo_id, query, max_results)
        if results:
            return results
        return self._find_by_keyword(repo_id, query, max_results)

    def _find_by_embedding(
        self,
        repo_id: str,
        query: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """Vector retrieval plus a one-hop expansion through the graph."""
        try:
            from app.db.vector_store import OVERSAMPLE_FACTOR, VECTOR_INDEX_NAME
        except Exception as e:  # pragma: no cover - import guard
            logger.warning(f"Embedding retrieval unavailable: {e}")
            return []

        if self.embedder is None:
            # Imported lazily: loading sentence-transformers is expensive and
            # only needed the first time a question is asked.
            try:
                from app.services.embeddings import CodeEmbedder

                self.embedder = CodeEmbedder()
            except Exception as e:
                logger.warning(f"Could not load embedder for Q&A retrieval: {e}")
                return []

        if not self.neo4j_driver:
            return []

        try:
            query_vector = [float(x) for x in self.embedder.embed_query(query)]
        except Exception as e:
            logger.warning(f"Could not embed question: {e}")
            return []

        cypher = (
            f"CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', $k, $qvec)\n"
            "YIELD node, score\n"
            "WHERE node.repoId = $repo_id\n"
            "WITH node, score ORDER BY score DESC LIMIT $max_nodes\n"
            "OPTIONAL MATCH (node)-[r:RELATION]-(m:Node)\n"
            "WHERE r.type IN ['calls', 'imports', 'defines']\n"
            "RETURN node, score,\n"
            "       collect(DISTINCT {relation: r.type, target: m.name, path: m.path})[..8]\n"
            "         AS relations"
        )

        try:
            with self.neo4j_driver.session() as session:
                records = session.run(
                    cypher,
                    qvec=query_vector,
                    repo_id=repo_id,
                    k=max_results * OVERSAMPLE_FACTOR,
                    max_nodes=max_results,
                )
                return [
                    {
                        "node": dict(record["node"]),
                        "relations": [r for r in (record["relations"] or []) if r.get("relation")],
                        "relevance_score": float(record["score"]),
                    }
                    for record in records
                ]
        except Exception as e:
            logger.warning(f"Vector retrieval failed, falling back to keywords: {e}")
            return []

    def _find_by_keyword(
        self,
        repo_id: str,
        query: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """Name-substring retrieval, used when no embeddings are available."""
        if not self.neo4j_driver:
            return []

        keywords = [word.lower() for word in query.split() if len(word) > 3]
        results = []

        with self.neo4j_driver.session() as session:
            for keyword in keywords:
                # Edges are stored as a single :RELATION type with the real
                # kind ('calls', 'imports', 'defines') in r.type, so type(r)
                # would label every neighbour "RELATION".
                cypher_query = """
                MATCH (n)
                WHERE n.repoId = $repo_id
                  AND (
                    toLower(n.name) CONTAINS $keyword
                    OR toLower(n.type) CONTAINS $keyword
                  )
                OPTIONAL MATCH (n)-[r:RELATION]->(m)
                RETURN n, collect({relation: r.type, target: m.name, path: m.path})[..10] AS relations
                LIMIT $limit
                """

                result = session.run(
                    cypher_query,
                    repo_id=repo_id,
                    keyword=keyword,
                    limit=max_results
                )

                for record in result:
                    node = dict(record["n"])
                    relations = [r for r in (record["relations"] or []) if r.get("relation")]
                    results.append({
                        "node": node,
                        "relations": relations,
                        "relevance_score": 1.0,  # Placeholder
                    })

        # Remove duplicates and limit results
        seen_ids = set()
        unique_results = []
        for item in results:
            node_id = item["node"].get("id")
            if node_id and node_id not in seen_ids:
                seen_ids.add(node_id)
                unique_results.append(item)
                if len(unique_results) >= max_results:
                    break

        return unique_results

    def format_context_from_nodes(
        self,
        nodes: List[Dict[str, Any]],
        include_relations: bool = True,
    ) -> str:
        """
        Format code context from graph nodes for LLM prompt.

        Args:
            nodes: List of node dicts from find_relevant_code
            include_relations: Whether to include relationships

        Returns:
            Formatted context string
        """
        if not nodes:
            return "No relevant code found."

        context_parts = []

        for i, item in enumerate(nodes, 1):
            node = item["node"]
            node_type = node.get("type", "unknown")
            name = node.get("name", "unknown")
            path = node.get("path", "")
            code = node.get("code", "")

            # Format code element
            context_parts.append(f"### {i}. {node_type.capitalize()}: {name}")
            if path:
                context_parts.append(f"**File:** {path}")

            if code:
                # Truncate long code
                if len(code) > 500:
                    code = code[:500] + "\n... (truncated)"
                context_parts.append(f"```\n{code}\n```")

            # Add relations if available and requested
            if include_relations and item.get("relations"):
                relations = item["relations"]
                if relations:
                    relation_strs = []
                    for rel in relations[:5]:  # Limit to 5 relations
                        rel_type = rel.get("relation", "")
                        target = rel.get("target")
                        # 'target' is the neighbour's name
                        target_name = target if isinstance(target, str) else (
                            (target or {}).get("name")
                        )
                        if rel_type and target_name:
                            relation_strs.append(f"{rel_type} → {target_name}")

                    if relation_strs:
                        context_parts.append(f"**Relations:** {', '.join(relation_strs)}")

            context_parts.append("")  # Empty line between elements

        return "\n".join(context_parts)

    def answer_question(
        self,
        repo_id: str,
        question: str,
        max_context_nodes: int = 5,
        include_call_graph: bool = True,
    ) -> Dict[str, Any]:
        """
        Answer a question about the codebase using RAG.

        Args:
            repo_id: Repository ID
            question: User's question
            max_context_nodes: Maximum code nodes to include in context
            include_call_graph: Whether to include call graph in context

        Returns:
            Dict with 'answer', 'sources', 'cost', etc.
        """
        # Step 1: Retrieve relevant code
        relevant_nodes = self.find_relevant_code(repo_id, question, max_context_nodes)

        if not relevant_nodes:
            return {
                "answer": "I couldn't find relevant code to answer this question. The codebase might not contain information related to your query, or the repository data might not be fully indexed yet.",
                "sources": [],
                "context_used": 0,
            }

        # Step 2: Format context
        code_context = self.format_context_from_nodes(relevant_nodes, include_relations=include_call_graph)

        # Step 3: Generate answer using LLM
        messages = [
            {
                "role": "system",
                "content": prompts.SYSTEM_PROMPT_QA
            },
            {
                "role": "user",
                "content": prompts.PROMPT_QA_WITH_CONTEXT.format(
                    question=question,
                    context=code_context
                )
            }
        ]

        response = self.client.chat_completion(
            messages,
            temperature=0.2,  # Slightly higher for more natural responses
            max_tokens=1000,
        )

        # Extract sources
        sources = []
        for item in relevant_nodes:
            node = item["node"]
            sources.append({
                "type": node.get("type"),
                "name": node.get("name"),
                "path": node.get("path"),
                "id": node.get("id"),
            })

        return {
            "answer": response["content"],
            "sources": sources,
            "context_used": len(relevant_nodes),
            "cost": response.get("cost", 0),
            "from_cache": response.get("from_cache", False),
        }

    def explain_function(
        self,
        repo_id: str,
        function_name: str,
        detailed: bool = False,
    ) -> Dict[str, Any]:
        """
        Explain a specific function in detail.

        Args:
            repo_id: Repository ID
            function_name: Name of function to explain
            detailed: Whether to include detailed explanation

        Returns:
            Dict with explanation and context
        """
        if not self.neo4j_driver:
            return {"error": "Neo4j driver not available"}

        # Find the function in the graph
        with self.neo4j_driver.session() as session:
            cypher_query = """
            MATCH (f)
            WHERE f.repoId = $repo_id
              AND f.type = 'function'
              AND f.name = $function_name
            OPTIONAL MATCH (f)-[r:calls]->(called)
            RETURN f, collect({name: called.name, type: called.type}) as calls
            LIMIT 1
            """

            result = session.run(
                cypher_query,
                repo_id=repo_id,
                function_name=function_name
            )

            record = result.single()
            if not record:
                return {"error": f"Function '{function_name}' not found"}

            func_node = dict(record["f"])
            calls = record["calls"]

        # Format context
        code = func_node.get("code", "")
        path = func_node.get("path", "")

        call_graph_str = ""
        if calls:
            call_list = [f"  - {call['name']}" for call in calls if call.get('name')]
            call_graph_str = "\n".join(call_list)

        context = f"File: {path}"
        if call_graph_str:
            context += f"\nCalls: \n{call_graph_str}"

        # Choose prompt based on detail level
        if detailed:
            prompt_template = prompts.PROMPT_EXPLAIN_CODE
        else:
            prompt_template = prompts.PROMPT_SUMMARIZE_FUNCTION

        messages = [
            {
                "role": "system",
                "content": prompts.SYSTEM_PROMPT_CODE_EXPERT
            },
            {
                "role": "user",
                "content": prompt_template.format(
                    language=func_node.get("language", "python"),
                    context=context,
                    code=code
                )
            }
        ]

        response = self.client.chat_completion(
            messages,
            max_tokens=500 if not detailed else 1500,
        )

        return {
            "function": function_name,
            "explanation": response["content"],
            "file": path,
            "calls": calls,
            "cost": response.get("cost", 0),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get Q&A system statistics"""
        return self.client.get_stats()
