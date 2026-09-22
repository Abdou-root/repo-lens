# RepoLens — suggested fixes, explained

Written 2026-09-22 after reading `github.com/Abdou-root/repo-lens` at commit `5324204`.
Fix #1's bug was **reproduced by running your real `PythonParser`** on a test file
(Tree-sitter 0.23 with a small compatibility shim, because 0.21 doesn't build on
Python 3.13). Everything else comes from reading the code; the Docker stack wasn't run.

Why the app "mostly worked" when you tested it: every feature you could click
(clone → graph, insights, node drawer, Q&A chat) runs through Neo4j, which is
shared by all processes. The broken part, embedding search, was **never wired into
the UI** — `GraphExplorer.tsx` defines `_performSemanticSearch` but never calls it
(note the `_` prefix and the `eslint-disable no-unused-vars`). The search box does
`node.name.toLowerCase().includes(query)` in the browser. So the bugs below are
real but invisible from the UI.

Order = impact per hour of work.

---

## 1. `from x import y` loses the module (≈20 min) — CONFIRMED BY RUNNING IT

**File:** `app/services/parsers/python_parser.py`, `extract_imports`, the
`import_from_statement` branch.

**What happens.** In Tree-sitter's Python grammar, `from a.b import c, d` has
*three* `dotted_name` children: `a.b` (field `module_name`), `c` and `d` (field
`name`). Your loop checks `if child.type == "dotted_name": module = ...` first, so
every name overwrites `module`, and the later
`elif child.type == "dotted_name" and ...` branch can never run (same condition,
already taken). Result, from the real parser:

```
from app.services.parser import parse_repository, _resolve_calls
  -> module='_resolve_calls'  names=[]          # module path lost
```

`_resolve_imports` then looks up `_resolve_calls` as a module, finds nothing, and
marks the edge `external`. **Most Python import edges in a from-import-heavy repo
are wrong.**

**Fix.** Ask for children *by field name* instead of by node type:

```python
elif node.type == "import_from_statement":
    module_node = node.child_by_field_name("module_name")
    module = self._get_text(module_node, source_code) if module_node else ""
    names, alias = [], None
    for child in node.children_by_field_name("name"):   # only the imported names
        if child.type == "aliased_import":
            n = child.child_by_field_name("name")
            a = child.child_by_field_name("alias")
            names.append(self._get_text(n, source_code))
            alias = self._get_text(a, source_code) if a else alias
        else:                                           # plain dotted_name
            names.append(self._get_text(child, source_code))
    imports.append(Import(module=module, names=names, alias=alias,
                          file_path=file_path, line_number=node.start_point[0] + 1))
```

Tested output with the fix:

```
module='app.services.parser'  names=['parse_repository', '_resolve_calls']
module='.'                    names=['utils']
module='..core.db'            names=['get_driver']  alias='gd'
```

Relative imports now keep their dots (`.`, `..core.db`), so the resolver can
resolve them against the importing file's folder:

```python
def resolve_relative(module: str, importer_path: str) -> str:
    """'..core.db' imported from 'app/api/search.py' -> 'app.core.db'"""
    dots = len(module) - len(module.lstrip("."))
    base = importer_path.replace("\\", "/").split("/")[:-1]   # folder of the importer
    base = base[: len(base) - (dots - 1)] if dots > 1 else base
    rest = module.lstrip(".")
    return ".".join(base + ([rest] if rest else []))
```

Call it in `_resolve_imports` when `target.startswith(".")`, then look the result up
in `module_to_file` as you already do.

---

## 2. Q&A context labels every relationship "RELATION" (≈5 min)

**File:** `app/services/llm/qa.py`, `find_relevant_code`.

Edges are written as `MERGE (s)-[rel:RELATION {id: r.id}]->(t) SET rel.type = r.type`
(`app/db/models.py`): the Neo4j relationship **type** is always `RELATION`, and the
real kind (`calls`, `imports`, `defines`) is a **property**. The Q&A query returns
`type(r)`, so the LLM is told every neighbour is related by "RELATION".

```cypher
-- before
OPTIONAL MATCH (n)-[r]->(m)
RETURN n, collect({relation: type(r), target: m}) as relations
-- after
OPTIONAL MATCH (n)-[r:RELATION]->(m)
RETURN n, collect({relation: r.type, target: m.name})[..10] AS relations
```

The `[..10]` also stops one hub node from flooding the prompt.

---

## 3. Make embedding search real: store vectors in Neo4j (≈half a day)

**Why it's broken today.** `SemanticSearch` keeps vectors in a Python list
(`self._code_index`). The worker fills *its* copy inside `_generate_embeddings_for_repo`.
RQ's default `Worker` also forks a child process per job, so that list dies when
the job ends. The API has its own empty copy (`app/api/search.py: get_search_service`).
This is true in Docker Compose and in your Railway `start.sh` alike (uvicorn and the
worker are two processes). Only `app/demo/data_loader.py` indexes inside the API
process, which is why demo search can work and user repos can't. Two smaller bugs sit
on the same path:
- `language="python"` is hard-coded in the worker, even for TypeScript functions.
- The index metadata has no `node_id`, but the frontend reads `r.metadata.node_id`.

**Idea.** Every process already talks to Neo4j, so put the vector on the node and
let Neo4j do the nearest-neighbour search. Neo4j 5 has a built-in vector index.

**Step 1 — upgrade Neo4j.** Your compose file pins `neo4j:5.8`; vector indexes need
5.11+ and the `CREATE VECTOR INDEX` syntax needs 5.15+. Use the LTS:

```yaml
neo4j:
  image: neo4j:5.26
```

(Neo4j Aura is already on a new enough version.)

**Step 2 — create the index** in `ensure_indexes()` (`app/db/models.py`).
`all-MiniLM-L6-v2` produces 384-dimensional vectors:

```cypher
CREATE VECTOR INDEX code_embeddings IF NOT EXISTS
FOR (n:Node) ON (n.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 384,
  `vector.similarity_function`: 'cosine'
}}
```

**Step 3 — the worker writes vectors to the nodes** instead of a local list
(`app/worker/tasks.py`). Batch it: `embed_batch` is much faster than one call per
node, and one `UNWIND` per 200 rows is far cheaper than 200 round-trips.

```python
LANG_BY_EXT = {".py": "python", ".ts": "typescript", ".tsx": "typescript",
               ".js": "javascript", ".jsx": "javascript"}

def _generate_embeddings_for_repo(repo_id, nodes, ctx):
    embedder = get_embedder()
    todo = [n for n in nodes if n.get("type") in ("function", "class")]
    for i in range(0, len(todo), 200):
        batch = todo[i:i + 200]
        texts = [f"{n['type']} {n['name']}\n{n.get('summary') or ''}\n{n.get('code', '')}"
                 for n in batch]
        vectors = embedder.embed_batch(texts)            # -> np.ndarray, shape (len, 384)
        rows = [{"id": n["id"], "embedding": v.tolist(),
                 "language": LANG_BY_EXT.get(os.path.splitext(n.get("path", ""))[1], "unknown")}
                for n, v in zip(batch, vectors)]
        run_query(
            """
            UNWIND $rows AS r
            MATCH (n:Node {id: r.id})
            SET n.language = r.language
            WITH n, r
            CALL db.create.setNodeVectorProperty(n, 'embedding', r.embedding)
            """,
            {"rows": rows},
        )
        publish_progress_detailed(ctx, 40 + int(35 * (i + len(batch)) / max(1, len(todo))),
                                  f"Embedded {i + len(batch)}/{len(todo)} code elements")
    ...
```

`db.create.setNodeVectorProperty` stores the list as a compact float array (a plain
`SET n.embedding = r.embedding` also works but uses more space).

**Step 4 — the API queries the index** (`app/api/search.py`). Embed the query with
the *same* model, then ask Neo4j for the nearest nodes:

```python
query_vec = embedder.embed_query(request.query).tolist()
rows = run_query(
    """
    CALL db.index.vector.queryNodes('code_embeddings', $k, $vec) YIELD node, score
    WHERE node.repoId = $repo_id AND score >= $threshold
    RETURN node.id AS node_id, node.name AS name, node.type AS type,
           node.path AS path, node.language AS language, score
    ORDER BY score DESC LIMIT $top_k
    """,
    {"vec": query_vec, "repo_id": request.repo_id, "threshold": request.similarity_threshold,
     "k": request.top_k * 10, "top_k": request.top_k},
)
```

Why `k = top_k * 10`: the vector index is **global** across all repos. It returns
the k nearest nodes first, and *then* the `WHERE repoId` filter runs. Ask for more
than you need, or small repos get crowded out by big ones.

**Step 5 — wire the UI.** In `GraphExplorer.tsx`, call `_performSemanticSearch`
(rename it without the `_`) when the user toggles a "Semantic" mode, or when the
name search finds nothing. Return `node_id` at the top level of each result and read
`r.node_id` instead of `r.metadata.node_id`.

Now the embeddings survive restarts, every process sees the same data, and the
in-memory `SemanticSearch` index can be deleted.

---

## 4. Retrieve Q&A context with embeddings + one graph hop (≈1 hour, after #3)

`find_relevant_code` splits the question into words longer than 3 letters and runs
`toLower(n.name) CONTAINS $keyword` for each. "How is the user logged in?" finds
nothing unless a function is literally named `login`. Once #3 exists:

```cypher
CALL db.index.vector.queryNodes('code_embeddings', $k, $qvec) YIELD node, score
WHERE node.repoId = $repo_id
WITH node, score ORDER BY score DESC LIMIT $max_nodes
OPTIONAL MATCH (node)-[r:RELATION]-(m:Node)
WHERE r.type IN ['calls', 'imports', 'defines']
RETURN node, score,
       collect(DISTINCT {relation: r.type, target: m.name, path: m.path})[..8] AS relations
```

This is the "retrieve by meaning, then expand through the graph" pattern (often
called GraphRAG), and it's the honest version of the README's "grounded in its actual
context". It's also a strong interview talking point: *why a graph beats plain vector
RAG for code* — the answer usually lives in the caller or callee, not in the chunk
that matched.

---

## 5. Call resolution: stop guessing (≈1–2 hours)

**File:** `app/services/parser.py`, `_resolve_calls`.

Today a call to `run` resolves to the same-file `run` if there is one, otherwise to
**the first `run` anywhere in the repo**. In a repo with ten `run` functions, nine
calls are wired to the wrong code, and the graph looks confident about it.

Resolve in the order a Python interpreter would, and leave the call unresolved when
you can't tell:

```python
def resolve_callee(callee, caller_file, funcs_by_file, imports_by_file, module_to_file):
    # 1. defined in the same file
    if callee in funcs_by_file.get(caller_file, {}):
        return funcs_by_file[caller_file][callee]
    # 2. imported by name into this file:  from mod import callee
    for imp in imports_by_file.get(caller_file, []):
        if callee in imp.names or callee == imp.alias:
            target_file = module_to_file.get(imp.module)          # needs fix #1
            if target_file and callee in funcs_by_file.get(target_file, {}):
                return funcs_by_file[target_file][callee]
    # 3. unique across the whole repo
    matches = [ids[callee] for ids in funcs_by_file.values() if callee in ids]
    if len(matches) == 1:
        return matches[0]
    return None   # ambiguous: mark 'external' — a missing edge is better than a wrong one
```

`funcs_by_file` is `{path: {func_name: node_id}}`, built from the nodes you already
have. `imports_by_file` means keeping the `Import` objects per file from parsing,
which the current pipeline throws away after turning them into edges.

---

## 6. Tests (≈2 hours for a meaningful first set)

`pytest` is in `requirements.txt`, but there isn't a single test. The parsers are pure
functions over strings, so they're the easiest thing to test and the most valuable
(fix #1 would have been caught on day one). `tests/test_python_parser.py`:

```python
import pytest
from app.services.parsers.python_parser import PythonParser

@pytest.fixture
def parser():
    return PythonParser()

def test_from_import_keeps_module_and_names(parser):
    imps = parser.extract_imports("from a.b import c, d as e\n", "x.py")
    assert imps[0].module == "a.b"
    assert imps[0].names == ["c", "d"]
    assert imps[0].alias == "e"

def test_relative_import_keeps_dots(parser):
    imps = parser.extract_imports("from ..core import db\n", "pkg/api/x.py")
    assert imps[0].module == "..core"

def test_calls_are_attributed_to_the_calling_function(parser):
    src = "def helper():\n    pass\n\ndef run():\n    helper()\n"
    calls = parser.extract_calls(src, "x.py")
    assert ("run", "helper") in {(c.caller, c.callee) for c in calls}
```

The first two **fail today** and pass after fix #1. That's what a test is for.
Then add one end-to-end test that feeds `_resolve_imports` / `_resolve_calls` a tiny
three-file repo and asserts the exact edges (fix #5).

---

## 7. Security and hygiene (≈15 min)

- `docker-compose.yml`: `${NEO4J_PASSWORD:-u9H471...}` → `${NEO4J_PASSWORD:?set NEO4J_PASSWORD in .env}`.
  The `:?` form makes Compose refuse to start without a password, instead of quietly
  using one that's published on GitHub. Change that password anywhere it was real.
- Delete the committed `__pycache__/` folders: `git rm -r --cached app/**/__pycache__`,
  then add `__pycache__/` and `*.pyc` to `.gitignore`.
- README: fix `git clone https://github.com/yourusername/repolens.git`.

---

## What this does to the rating

| After | Rating | Why |
|---|---|---|
| today | 6/10 | ambitious, real architecture; untested, search not real |
| #1, #2, #6, #7 (≈3 hours) | 7/10 | parser correct and proven by tests, no secrets |
| + #3, #4 | 8/10 | real GraphRAG over code — a genuinely strong AI-engineer project |
| + #5, screenshot, static demo | 8.5/10 | reviewers can see it and trust the graph |

Once #3 and #4 ship, tell me and the CVs get "semantic search" and "graph-grounded
Q&A" back as verified claims.
