import { useCallback, useState, useMemo, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  BackgroundVariant,
  MarkerType,
  useReactFlow,
  ReactFlowProvider,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import Dagre from '@dagrejs/dagre';
import { Header } from '@/components/layout/Header';
import { fetchDemoGraph, fetchDemoInsights, fetchDemoRepositories } from '@/lib/demoData';
import { GraphNode } from '@/types';
import { FileNode, ClassNode, FunctionNode, FolderNode } from '@/components/graph/CustomNodes';
import { NodeDrawer } from '@/components/graph/NodeDrawer';
import { ChatPanel } from '@/components/graph/ChatPanel';
import { InsightsPanel } from '@/components/graph/InsightsPanel';
import { CommandPalette } from '@/components/ui/CommandPalette';
import { NodeTooltip } from '@/components/graph/NodeTooltip';
import { GraphSkeleton } from '@/components/graph/GraphSkeleton';
import { ExportMenu } from '@/components/graph/ExportMenu';
import { HelpCenter } from '@/components/help/HelpCenter';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { ArrowLeft, Search, MessageSquare, LayoutGrid, LayoutList, FolderTree, Network, ChevronsDownUp, ChevronsUpDown, Filter, X, ChevronDown, ChevronUp, Lightbulb, Command, Sparkles, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { useCommandPaletteShortcut, useHelpCenterShortcut } from '@/hooks/useKeyboardShortcuts';
import { trackEvent, Events } from '@/lib/analytics';
import { updateSEO } from '@/lib/seo';
import { toast } from 'sonner';
import { getFolderPath, buildFolderHierarchy } from '@/lib/graph-utils';
import { EDGE_COLORS, LAYOUT_CONFIG } from '@/lib/graph-constants';

const nodeTypes = {
  file: FileNode,
  class: ClassNode,
  function: FunctionNode,
  folder: FolderNode,
};

// Use shared edge colors
const edgeColors = EDGE_COLORS;

/**
 * Apply Dagre hierarchical layout to nodes and edges.
 * Groups files by folders for a cleaner visualization.
 */
function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  collapsedFolders: Set<string>,
  direction: 'TB' | 'LR' = 'LR'
): { nodes: Node[]; edges: Edge[] } {
  const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));

  g.setGraph({
    rankdir: direction,
    nodesep: LAYOUT_CONFIG.nodeSep,
    ranksep: LAYOUT_CONFIG.rankSep,
  });

  // Separate folder nodes from content nodes
  const folderNodes = nodes.filter(n => n.type === 'folder');
  const contentNodes = nodes.filter(n => n.type !== 'folder');

  // Add folder nodes first
  folderNodes.forEach((node) => {
    g.setNode(node.id, {
      width: LAYOUT_CONFIG.folderWidth,
      height: LAYOUT_CONFIG.folderHeight,
    });
  });

  // Add content nodes
  contentNodes.forEach((node) => {
    // Skip nodes in collapsed folders
    const nodeData = node.data as { folderPath?: string };
    if (nodeData.folderPath && collapsedFolders.has(nodeData.folderPath)) {
      return;
    }

    g.setNode(node.id, {
      width: LAYOUT_CONFIG.nodeWidth,
      height: LAYOUT_CONFIG.nodeHeight,
    });
    // Note: We don't use setParent() - React Flow doesn't support compound node rendering
    // Visual grouping is achieved via containment edges (dashed lines from folders to children)
  });

  // Add edges (only for visible nodes that exist in the graph)
  edges.forEach((edge) => {
    const hasSource = g.hasNode(edge.source);
    const hasTarget = g.hasNode(edge.target);
    if (hasSource && hasTarget) {
      g.setEdge(edge.source, edge.target);
    }
  });

  // Calculate layout (only if we have nodes)
  const nodeCount = g.nodeCount();
  if (nodeCount > 0) {
    // Validate graph structure before layout
    const graphNodes = g.nodes();
    const graphEdges = g.edges();
    const hasValidStructure = graphNodes.length > 0 && 
      graphEdges.every(e => g.hasNode(e.v) && g.hasNode(e.w));
    
    if (hasValidStructure) {
      try {
        Dagre.layout(g);
      } catch (error) {
        if (!import.meta.env.PROD) {
          console.warn('Dagre layout failed:', error);
          console.warn('Graph nodes:', graphNodes.length);
          console.warn('Graph edges:', graphEdges.length);
        }
        // Return nodes with default positions if layout fails
        return { nodes, edges };
      }
    } else {
      // Invalid graph structure - return default positions
      if (!import.meta.env.PROD) {
        console.warn('Invalid graph structure, skipping layout');
      }
      return { nodes, edges };
    }
  }

  // Apply calculated positions
  const layoutedNodes = nodes
    .filter(node => {
      // Filter out nodes in collapsed folders
      if (node.type === 'folder') return true;
      const nodeData = node.data as { folderPath?: string };
      return !nodeData.folderPath || !collapsedFolders.has(nodeData.folderPath);
    })
    .map((node) => {
      const nodeWithPosition = g.node(node.id);
      if (nodeWithPosition) {
        const width = node.type === 'folder' ? LAYOUT_CONFIG.folderWidth : LAYOUT_CONFIG.nodeWidth;
        const height = node.type === 'folder' ? LAYOUT_CONFIG.folderHeight : LAYOUT_CONFIG.nodeHeight;
        return {
          ...node,
          position: {
            x: nodeWithPosition.x - width / 2,
            y: nodeWithPosition.y - height / 2,
          },
        };
      }
      return node;
    });

  // Filter edges for visible nodes
  const visibleNodeIds = new Set(layoutedNodes.map(n => n.id));
  const layoutedEdges = edges.filter(e => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target));

  return { nodes: layoutedNodes, edges: layoutedEdges };
}

interface GraphResponse {
  nodes: GraphNode[];
  edges: import('@/types').GraphEdge[];
}

// Inner component that uses useReactFlow (must be inside ReactFlowProvider)
function GraphExplorerInner() {
  const { repoId } = useParams<{ repoId: string }>();
  const navigate = useNavigate();
  const { isDemoMode } = useAuth();
  const { fitView } = useReactFlow();
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [chatNodeContext, setChatNodeContext] = useState<GraphNode | null>(null); // Separate state for chat context
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
  const [chatOpen, setChatOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [semanticSearchResults, setSemanticSearchResults] = useState<Array<{ node_id: string; similarity: number; type?: string; language?: string }>>([]);
  const [isSearching, setIsSearching] = useState(false);
  // 'name' matches node names in the browser; 'semantic' asks the backend
  // for the nearest code by meaning. Name search falls back to semantic
  // when it finds nothing.
  const [searchMode, setSearchMode] = useState<'name' | 'semantic'>('name');
  const [focusMode, _setFocusMode] = useState<'all' | 'neighbors'>('all');
  const [typeFilter, setTypeFilter] = useState<'file' | 'class' | 'function' | null>(null);
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const [layoutDirection, setLayoutDirection] = useState<'TB' | 'LR'>(() => {
    const saved = localStorage.getItem(`repolens_layout_${repoId}`);
    return (saved as 'TB' | 'LR') || 'LR';
  });
  const [viewMode, setViewMode] = useState<'folder' | 'flat'>(() => {
    const saved = localStorage.getItem(`repolens_view_mode_${repoId}`);
    return (saved as 'folder' | 'flat') || 'folder';
  });
  const [filterFolder, setFilterFolder] = useState<string | null>(null);
  const [folderPathsRef, setFolderPathsRef] = useState<Set<string>>(new Set());

  // Simple search filters (setters unused - prepared for future UI)
  const [searchTypeFilters, _setSearchTypeFilters] = useState<Set<string>>(new Set(['function', 'class', 'file']));
  const [searchLanguageFilter, _setSearchLanguageFilter] = useState<string>('all');

  // Hardcoded sensible defaults (removed UI controls)
  // Neo4j normalises cosine similarity to (1 + cos) / 2, so unrelated code
  // scores around 0.5 and a threshold at or below 0.5 filters nothing.
  const SIMILARITY_THRESHOLD = 0.65;
  const TOP_K_RESULTS = 20;

  // Insights panel
  const [showInsights, setShowInsights] = useState(false);

  // Command palette
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  // Help center
  const [helpCenterOpen, setHelpCenterOpen] = useState(false);

  // Legend visibility
  const [legendCollapsed, setLegendCollapsed] = useState(() => {
    const saved = localStorage.getItem(`repolens_legend_collapsed_${repoId}`);
    return saved === 'true';
  });

  // Node tooltip state
  const [hoveredNode, setHoveredNode] = useState<{ node: GraphNode; position: { x: number; y: number } } | null>(null);

  // Keyboard navigation state
  const [focusedNodeIndex, setFocusedNodeIndex] = useState<number>(-1);

  // Ref to track current node request for race condition handling
  const currentNodeRequestRef = useRef<AbortController | null>(null);

  // Ref for export functionality
  const reactFlowWrapperRef = useRef<HTMLDivElement>(null);

  // Register Cmd+K shortcut
  useCommandPaletteShortcut(() => setCommandPaletteOpen(true));

  // Register ? shortcut for help center
  useHelpCenterShortcut(() => setHelpCenterOpen(true));

  // Fetch graph data from the backend, or from pre-parsed static files in demo mode
  const { data: graphData, isLoading, error } = useQuery({
    queryKey: ['graph', repoId, isDemoMode],
    queryFn: () => isDemoMode
      ? fetchDemoGraph(repoId!)
      : api.get<GraphResponse>(`/api/graph/${repoId}`),
    enabled: !!repoId,
    staleTime: 5 * 60 * 1000,  // Cache for 5 minutes - don't refetch on navigation
    gcTime: 10 * 60 * 1000,  // Keep in cache for 10 minutes
    refetchOnWindowFocus: false,  // Don't refetch when window regains focus
    refetchOnMount: false,  // Don't refetch on component remount if data is fresh
  });

  // Fetch insights
  const { data: insightsData, isLoading: insightsLoading } = useQuery({
    queryKey: ['insights', repoId, isDemoMode],
    queryFn: () => isDemoMode
      ? fetchDemoInsights<any>(repoId!)
      : api.get<any>(`/api/repos/${repoId}/insights`),
    enabled: !!repoId && showInsights,  // Only fetch when panel is open
    staleTime: 5 * 60 * 1000,  // Cache for 5 minutes
    gcTime: 10 * 60 * 1000,  // Keep in cache for 10 minutes
  });

  // Get repo info for display (name, etc.)
  const { data: demoRepositories = [] } = useQuery({
    queryKey: ['demo-repos'],
    queryFn: fetchDemoRepositories,
    enabled: isDemoMode,
  });
  const repo = isDemoMode
    ? demoRepositories.find((r) => r.id === repoId)
    : null;

  const graphNodes = graphData?.nodes || [];
  const graphEdges = graphData?.edges || [];

  // Track graph viewed and update SEO
  useEffect(() => {
    if (graphData && repoId) {
      trackEvent(Events.GRAPH_VIEWED, {
        repo_id: repoId,
        node_count: graphNodes.length,
        edge_count: graphEdges.length,
      });
      
      // Update SEO for graph page
      updateSEO({
        title: `Graph: ${repo?.name || repoId}`,
        description: `Interactive code dependency graph with ${graphNodes.length} nodes and ${graphEdges.length} connections`,
        url: window.location.href,
      });
    }
    
    return () => {
      // Reset SEO on unmount
      import('@/lib/seo').then(({ resetSEO }) => resetSEO());
    };
  }, [graphData, repoId, graphNodes.length, graphEdges.length, repo?.name]);

  // Toggle folder collapse state
  const toggleFolderCollapse = useCallback((folderPath: string) => {
    setCollapsedFolders(prev => {
      const next = new Set(prev);
      if (next.has(folderPath)) {
        next.delete(folderPath);
      } else {
        next.add(folderPath);
      }
      return next;
    });
  }, []);

  // Apply focus mode filtering - memoized for performance
  const applyFocusMode = useCallback((nodes: Node[]) => {
    // Only filter if typeFilter is set
    if (typeFilter) {
      return nodes.filter(n => {
        // Always keep folders
        if (n.type === 'folder') return true;
        // Filter by type
        return n.type === typeFilter;
      });
    }

    // Otherwise show all nodes - highlighting via highlightedNodes provides visual context
    return nodes;
  }, [typeFilter]);

  // Memoize node/edge counts for performance (prepared for future use)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const graphStats = useMemo(() => ({
    nodeCount: graphNodes.length,
    edgeCount: graphEdges.length,
    fileCount: graphNodes.filter(n => n.type === 'file').length,
    classCount: graphNodes.filter(n => n.type === 'class').length,
    functionCount: graphNodes.filter(n => n.type === 'function').length,
  }), [graphNodes, graphEdges]);

  // Extract folder paths separately to avoid side effects in useMemo
  const folderPaths = useMemo(() => {
    const paths = new Set<string>();
    graphNodes.forEach((node) => {
      if (node.path) {
        const folderPath = getFolderPath(node.path);
        paths.add(folderPath);
      }
    });
    return paths;
  }, [graphNodes]);

  // Update folderPathsRef when folder paths change (separate effect to avoid side effects in useMemo)
  useEffect(() => {
    setFolderPathsRef(folderPaths);
  }, [folderPaths]);

  // Convert to React Flow format with folder grouping and Dagre layout
  const { layoutedNodes: initialNodes, layoutedEdges: initialEdges } = useMemo(() => {
    // Count ALL nodes per folder (not just files)
    const folderChildCounts = new Map<string, number>();
    graphNodes.forEach((node) => {
      if (node.path) {
        const folderPath = getFolderPath(node.path);
        folderChildCounts.set(folderPath, (folderChildCounts.get(folderPath) || 0) + 1);
      }
    });

    // Build folder hierarchy for parent-child relationships
    const folderHierarchy = buildFolderHierarchy(folderPaths);

    // Helper to check if a folder or its ancestors are collapsed
    const isFolderHidden = (path: string): boolean => {
      if (collapsedFolders.has(path)) return false; // The folder itself is visible
      // Check if any ancestor is collapsed
      let current = path;
      while (current !== '.') {
        const parent = getFolderPath(current + '/dummy');
        if (parent === current) break;
        if (collapsedFolders.has(parent)) return true;
        current = parent;
      }
      return false;
    };

    // Create folder nodes (only in folder view mode)
    const folderNodes: Node[] = viewMode === 'folder'
      ? Array.from(folderPaths)
        .filter(folderPath => !isFolderHidden(folderPath))
        .filter(folderPath => !filterFolder || folderPath.startsWith(filterFolder) || filterFolder.startsWith(folderPath))
        .map((folderPath) => ({
          id: `folder-${folderPath}`,
          type: 'folder',
          position: { x: 0, y: 0 },
          data: {
            name: folderPath === '.' ? 'root' : folderPath.split('/').pop() || folderPath,
            path: folderPath,
            childCount: folderChildCounts.get(folderPath) || 0,
            isCollapsed: collapsedFolders.has(folderPath),
            onToggleCollapse: () => toggleFolderCollapse(folderPath),
            highlighted: highlightedNodes.has(`folder-${folderPath}`),
          },
        }))
      : [];

    // Create content nodes (files, classes, functions) with folder assignment
    const contentNodes: Node[] = graphNodes
      .filter(node => !filterFolder || (node.path && node.path.startsWith(filterFolder)))
      .map((node) => {
        const nodeType = node.type.toLowerCase() as 'file' | 'class' | 'function';
        const folderPath = node.path ? getFolderPath(node.path) : null;

        // Find similarity score from semantic search results
        const searchResult = semanticSearchResults.find(r => r.node_id === node.id);
        const similarity = searchResult?.similarity;

        return {
          id: node.id,
          type: nodeType,
          position: { x: 0, y: 0 },
          data: {
            name: node.name,
            path: node.path,
            summary: node.summary,
            highlighted: highlightedNodes.has(node.id),
            similarity: similarity, // Add similarity score for visual intensity
            // Assign folderPath to ALL node types in folder view mode
            folderPath: viewMode === 'folder' ? folderPath : null,
          },
        };
      });

    // Combine folder and content nodes
    const rawNodes: Node[] = [...folderNodes, ...contentNodes];

    // Create edges with enhanced styling - optimized for large graphs
    const rawEdges: Edge[] = graphEdges.map((edge) => {
      const isHighlighted = highlightedNodes.has(edge.source) || highlightedNodes.has(edge.target);
      const edgeColor = edgeColors[edge.type] || edgeColors.external;
      const baseOpacity = highlightedNodes.size === 0 ? 0.6 : (isHighlighted ? 1 : 0.15);

      // For large graphs (>200 edges), simplify non-highlighted edges
      const isLargeGraph = graphEdges.length > 200;
      const shouldSimplify = isLargeGraph && !isHighlighted;

      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: shouldSimplify ? 'default' : 'smoothstep',
        animated: isHighlighted,
        label: isHighlighted ? edge.type : undefined,
        labelStyle: isHighlighted ? {
          fontSize: 10,
          fontWeight: 600,
          fill: edgeColor,
          opacity: 0.9,
        } : undefined,
        labelBgStyle: isHighlighted ? {
          fill: 'hsl(var(--background))',
          fillOpacity: 0.9,
        } : undefined,
        style: {
          stroke: edgeColor,
          strokeWidth: isHighlighted ? 3 : (shouldSimplify ? 1 : 1.5),
          opacity: baseOpacity,
          transition: shouldSimplify ? undefined : 'all 0.3s ease',
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: edgeColor,
          width: isHighlighted ? 24 : 20,
          height: isHighlighted ? 24 : 20,
        },
      };
    });

    // Add folder containment edges (folder -> children)
    const folderEdges: Edge[] = [];
    if (viewMode === 'folder') {
      // Add edges from folders to their direct file children
      contentNodes.forEach((node) => {
        const nodeData = node.data as { folderPath?: string };
        if (nodeData.folderPath && node.type === 'file') {
          const folderId = `folder-${nodeData.folderPath}`;
          const isHighlighted = highlightedNodes.has(folderId) || highlightedNodes.has(node.id);

          // Only add edge if folder node exists (not filtered out)
          if (rawNodes.some(n => n.id === folderId)) {
            folderEdges.push({
              id: `contains-${folderId}-${node.id}`,
              source: folderId,
              target: node.id,
              type: 'smoothstep',
              style: {
                stroke: 'hsl(var(--muted-foreground))',
                strokeWidth: isHighlighted ? 2 : 1,
                strokeDasharray: '6 3',
                opacity: isHighlighted ? 0.6 : 0.3,
                transition: 'all 0.3s ease',
              },
              markerEnd: {
                type: MarkerType.ArrowClosed,
                color: 'hsl(var(--muted-foreground))',
                width: 16,
                height: 16,
              },
            });
          }
        }
      });

      // Add edges from parent folders to child folders
      folderHierarchy.forEach((parentPath, folderPath) => {
        if (parentPath !== null) {
          const parentId = `folder-${parentPath}`;
          const childId = `folder-${folderPath}`;
          const isHighlighted = highlightedNodes.has(parentId) || highlightedNodes.has(childId);

          // Only add edge if both folders exist
          if (rawNodes.some(n => n.id === parentId) && rawNodes.some(n => n.id === childId)) {
            folderEdges.push({
              id: `hierarchy-${parentId}-${childId}`,
              source: parentId,
              target: childId,
              type: 'smoothstep',
              animated: isHighlighted,
              style: {
                stroke: 'hsl(var(--muted-foreground))',
                strokeWidth: isHighlighted ? 2.5 : 1.5,
                opacity: isHighlighted ? 0.7 : 0.4,
                transition: 'all 0.3s ease',
              },
              markerEnd: {
                type: MarkerType.ArrowClosed,
                color: 'hsl(var(--muted-foreground))',
                width: isHighlighted ? 20 : 16,
                height: isHighlighted ? 20 : 16,
              },
            });
          }
        }
      });
    }

    // Combine all edges - filter out edges that reference non-existent nodes
    const nodeIds = new Set(rawNodes.map(n => n.id));
    const validRawEdges = rawEdges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
    const allEdges = [...validRawEdges, ...folderEdges];

    // Apply focus mode filtering before layout
    const focusedNodes = applyFocusMode(rawNodes);

    // Filter edges to only include those between visible nodes
    const focusedNodeIds = new Set(focusedNodes.map(n => n.id));
    const focusedEdges = allEdges.filter(e => focusedNodeIds.has(e.source) && focusedNodeIds.has(e.target));

    // Apply Dagre layout with folder grouping
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      focusedNodes,
      focusedEdges,
      collapsedFolders,
      layoutDirection
    );

    return { layoutedNodes, layoutedEdges };
  }, [graphNodes, graphEdges, highlightedNodes, collapsedFolders, toggleFolderCollapse, layoutDirection, viewMode, filterFolder, folderPaths, semanticSearchResults, applyFocusMode]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Use refs to track if we need to sync
  const prevInitialNodesLength = useRef(initialNodes.length);
  const prevInitialEdgesLength = useRef(initialEdges.length);
  const prevLayoutDirection = useRef(layoutDirection);

  // Synchronize React Flow state when initialNodes/initialEdges change
  // This ensures the graph updates when:
  // - API data loads (first-click issue fix)
  // - viewMode toggles between folder/flat
  // - collapsedFolders changes (expand/collapse all)
  // - layoutDirection changes (horizontal/vertical toggle)
  // - Any other state that triggers useMemo recalculation
  useEffect(() => {
    // Check what changed to avoid infinite loops
    const nodesChanged = initialNodes.length !== prevInitialNodesLength.current;
    const edgesChanged = initialEdges.length !== prevInitialEdgesLength.current;
    const layoutChanged = layoutDirection !== prevLayoutDirection.current;

    if (nodesChanged || edgesChanged || layoutChanged) {
      setNodes(initialNodes);
      setEdges(initialEdges);
      prevInitialNodesLength.current = initialNodes.length;
      prevInitialEdgesLength.current = initialEdges.length;
      prevLayoutDirection.current = layoutDirection;

      // Re-fit view when layout changes to show the new arrangement
      if (layoutChanged && initialNodes.length > 0) {
        setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 100);
      }
    }
  }, [initialNodes, initialEdges, setNodes, setEdges, layoutDirection, fitView]);

  // Track if we've done the initial fit
  const [hasInitialFit, setHasInitialFit] = useState(false);

  // Track when to auto-send AI question
  const [autoSendQuestion, setAutoSendQuestion] = useState(false);

  // Center viewport after initial load - ONLY ONCE
  useEffect(() => {
    if (nodes.length > 0 && !hasInitialFit) {
      // Small delay to ensure nodes are rendered
      const timer = setTimeout(() => {
        fitView({ padding: 0.2, duration: 300 });
        setHasInitialFit(true);
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [nodes.length, hasInitialFit, fitView]); // Only fit view on initial load

  // Reset hasInitialFit when repo changes
  useEffect(() => {
    setHasInitialFit(false);
  }, [repoId]);

  // Persist layout preferences to localStorage
  useEffect(() => {
    if (repoId) {
      localStorage.setItem(`repolens_layout_${repoId}`, layoutDirection);
    }
  }, [layoutDirection, repoId]);

  useEffect(() => {
    if (repoId) {
      localStorage.setItem(`repolens_view_mode_${repoId}`, viewMode);
    }
  }, [viewMode, repoId]);

  useEffect(() => {
    if (repoId) {
      localStorage.setItem(`repolens_legend_collapsed_${repoId}`, legendCollapsed.toString());
    }
  }, [legendCollapsed, repoId]);

  const onNodeClick = useCallback(async (_: React.MouseEvent, node: Node) => {
    // Cancel previous request if still pending
    if (currentNodeRequestRef.current) {
      currentNodeRequestRef.current.abort();
    }

    // Handle folder nodes
    if (node.type === 'folder') {
      const folderData = node.data as { path: string; childCount: number; name: string };

      // Count nodes by type in this folder
      const nodesInFolder = graphNodes.filter(n =>
        n.path && getFolderPath(n.path) === folderData.path
      );
      const fileCount = nodesInFolder.filter(n => n.type.toLowerCase() === 'file').length;
      const classCount = nodesInFolder.filter(n => n.type.toLowerCase() === 'class').length;
      const functionCount = nodesInFolder.filter(n => n.type.toLowerCase() === 'function').length;

      // Create a virtual GraphNode for the folder
      const folderNode: GraphNode = {
        id: node.id,
        name: folderData.name,
        type: 'folder',
        path: folderData.path,
        summary: `${fileCount} files, ${classCount} classes, ${functionCount} functions`,
      };
      setSelectedNode(folderNode);

      // Highlight all nodes in this folder
      const highlightIds = new Set<string>([node.id, ...nodesInFolder.map(n => n.id)]);
      setHighlightedNodes(highlightIds);
      return;
    }

    const graphNode = graphNodes.find((n) => n.id === node.id);
    if (graphNode) {
      // Fetch detailed node data from backend if not in demo mode
      if (!isDemoMode && repoId) {
        const abortController = new AbortController();
        currentNodeRequestRef.current = abortController;

        try {
          const nodeDetails = await api.get<GraphNode>(
            `/api/graph/${repoId}/nodes/${node.id}`,
            { signal: abortController.signal }
          );

          // Only update if this request wasn't aborted
          if (!abortController.signal.aborted) {
            setSelectedNode(nodeDetails);
          }
        } catch (error) {
          // Ignore abort errors
          if (error instanceof Error && error.name === 'AbortError') {
            return;
          }

          if (!import.meta.env.PROD) {
            console.error('Failed to fetch node details:', error);
          }
          // Fallback to basic graph node data
          setSelectedNode(graphNode);
        } finally {
          // Clear ref if this was the current request
          if (currentNodeRequestRef.current === abortController) {
            currentNodeRequestRef.current = null;
          }
        }
      } else {
        setSelectedNode(graphNode);
      }

      const connectedIds = new Set<string>([node.id]);
      graphEdges.forEach((edge) => {
        if (edge.source === node.id) connectedIds.add(edge.target);
        if (edge.target === node.id) connectedIds.add(edge.source);
      });
      setHighlightedNodes(connectedIds);

      // Don't auto-change focus mode - highlighting shows the context
      // This prevents race condition where focusMode changes before selectedNode updates
    }
  }, [graphNodes, graphEdges, isDemoMode, repoId]);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setHighlightedNodes(new Set());
    setHoveredNode(null);
    // Keep current focus mode - don't force to 'all'
  }, []);

  const onNodeMouseEnter = useCallback((_: React.MouseEvent, node: Node) => {
    const graphNode = graphNodes.find((n) => n.id === node.id);
    if (graphNode) {
      // Get mouse position for tooltip placement
      const event = _ as unknown as MouseEvent;
      setHoveredNode({
        node: graphNode,
        position: { x: event.clientX, y: event.clientY }
      });
    }
  }, [graphNodes]);

  const onNodeMouseLeave = useCallback(() => {
    setHoveredNode(null);
  }, []);

  // Perform semantic search with filters
  const performSemanticSearch = useCallback(async (query: string) => {
    if (!query.trim() || !repoId) return;

    setIsSearching(true);
    try {
      // Build filter parameters
      const code_type = searchTypeFilters.size === 1 ? Array.from(searchTypeFilters)[0] : undefined;
      const language = searchLanguageFilter !== 'all' ? searchLanguageFilter : undefined;

      const response = await api.post<{ results: Array<{ node_id?: string; language?: string; similarity: number; metadata?: { node_id?: string; type?: string; language?: string } }> }>(
        '/api/search/semantic',
        {
          query,
          repo_id: repoId,
          top_k: TOP_K_RESULTS,
          similarity_threshold: SIMILARITY_THRESHOLD,
          code_type,
          language
        }
      );

      const results = response.results
        .map(r => ({
          node_id: r.node_id ?? r.metadata?.node_id ?? '',
          similarity: r.similarity,
          type: r.metadata?.type?.toLowerCase(),
          language: r.language ?? r.metadata?.language
        }))
        .filter(r => r.node_id);

      setSemanticSearchResults(results);

      // Highlight matching nodes
      const matchIds = new Set(results.map(r => r.node_id));
      setHighlightedNodes(matchIds);

      // Auto-fit view to show results
      if (results.length > 0) {
        setTimeout(() => {
          fitView({ padding: 0.2, duration: 500 });
        }, 100);
      }
    } catch (error) {
      if (!import.meta.env.PROD) {
        console.error('Semantic search failed:', error);
      }
      toast.error('Search failed. Please try again.');
      setHighlightedNodes(new Set()); // Clear any partial results
    } finally {
      setIsSearching(false);
    }
  }, [repoId, fitView, searchTypeFilters, searchLanguageFilter]);

  // Debounced search handler for performance
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (searchQuery.trim()) {
        // Semantic search needs the backend, which a static demo does not have
        if (searchMode === 'semantic' && !isDemoMode) {
          performSemanticSearch(searchQuery);
          return;
        }

        // Search ALL graph nodes, not just visible ones
        const matchingNodeIds = new Set<string>();
        const queryLower = searchQuery.toLowerCase();

        graphNodes.forEach(node => {
          if (node.name?.toLowerCase().includes(queryLower)) {
            matchingNodeIds.add(node.id);
          }
        });

        // No name matches: ask the backend for the nearest code by meaning
        if (matchingNodeIds.size === 0 && !isDemoMode) {
          performSemanticSearch(searchQuery);
          return;
        }

        // If matches found, expand folders containing matches
        if (matchingNodeIds.size > 0) {
          const foldersToExpand = new Set<string>();
          graphNodes.forEach(node => {
            if (matchingNodeIds.has(node.id) && node.path) {
              const folderPath = getFolderPath(node.path);
              if (collapsedFolders.has(folderPath)) {
                foldersToExpand.add(folderPath);
              }
            }
          });

          // Expand folders containing search results
          if (foldersToExpand.size > 0) {
            setCollapsedFolders(prev => {
              const next = new Set(prev);
              foldersToExpand.forEach(folder => next.delete(folder));
              return next;
            });
          }
        }

        setSemanticSearchResults([]);
        setHighlightedNodes(matchingNodeIds);
      } else {
        setSemanticSearchResults([]);
        setHighlightedNodes(new Set());
      }
    }, 300); // 300ms debounce

    return () => clearTimeout(timeoutId);
  }, [searchQuery, searchMode, isDemoMode, graphNodes, collapsedFolders, performSemanticSearch]);

  // Group semantic search results by type (prepared for future UI)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _groupedSearchResults = useMemo(() => {
    const groups: Record<string, Array<{ node_id: string; similarity: number; type?: string; language?: string }>> = {
      function: [],
      class: [],
      file: [],
      other: []
    };

    semanticSearchResults.forEach(result => {
      const type = result.type || 'other';
      if (groups[type]) {
        groups[type].push(result);
      } else {
        groups.other.push(result);
      }
    });

    return groups;
  }, [semanticSearchResults]);

  // Simple text search - filter nodes by name (prepared for future UI)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _filteredNodes = searchQuery
    ? nodes.filter((n) => (n.data as { name?: string }).name?.toLowerCase().includes(searchQuery.toLowerCase()))
    : nodes;

  // Keyboard navigation for graph nodes
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't handle keyboard navigation when typing in inputs or when modals are open
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable ||
        commandPaletteOpen ||
        helpCenterOpen ||
        chatOpen
      ) {
        return;
      }

      const visibleNodes = nodes.filter(n => n.type !== 'folder'); // Focus on content nodes only

      switch (e.key) {
        case 'Tab':
          e.preventDefault();
          // Move to next node
          const nextIndex = (focusedNodeIndex + 1) % visibleNodes.length;
          setFocusedNodeIndex(nextIndex);
          if (nextIndex >= 0 && nextIndex < visibleNodes.length) {
            const node = visibleNodes[nextIndex];
            const graphNode = graphNodes.find(n => n.id === node.id);
            if (graphNode) {
              setHoveredNode({
                node: graphNode,
                position: { x: 0, y: 0 }
              });
              // Highlight the node
              setHighlightedNodes(new Set([node.id]));
              // Center view on the node
              fitView({
                nodes: [node],
                padding: 0.3,
                duration: 300
              });
            }
          }
          break;

        case 'Enter':
          e.preventDefault();
          // Select the focused node
          if (focusedNodeIndex >= 0 && focusedNodeIndex < visibleNodes.length) {
            const node = visibleNodes[focusedNodeIndex];
            const mockEvent = {} as React.MouseEvent;
            onNodeClick(mockEvent, node);
          }
          break;

        case 'Escape':
          e.preventDefault();
          // Clear selection and focus
          setFocusedNodeIndex(-1);
          setSelectedNode(null);
          setHighlightedNodes(new Set());
          setHoveredNode(null);
          break;

        case '+':
        case '=':
          e.preventDefault();
          // Zoom in - handled by ReactFlow controls
          break;

        case '-':
        case '_':
          e.preventDefault();
          // Zoom out - handled by ReactFlow controls
          break;

        case '0':
          e.preventDefault();
          // Reset zoom
          fitView({ padding: 0.2, duration: 300 });
          break;

        case 'f':
        case 'F':
          e.preventDefault();
          // Fit view to all nodes
          fitView({ padding: 0.2, duration: 500 });
          break;

        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [focusedNodeIndex, nodes, graphNodes, commandPaletteOpen, helpCenterOpen, chatOpen, onNodeClick, fitView]);

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      if (currentNodeRequestRef.current) {
        currentNodeRequestRef.current.abort();
      }
    };
  }, []);

  // Show loading state with skeleton
  if (isLoading) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <Header />
        <div className="border-b border-border p-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
            <div className="h-4 w-px bg-border" />
            <span className="font-medium">{repo?.name || repoId || 'Repository'}</span>
          </div>
        </div>
        <div className="flex-1">
          <GraphSkeleton />
        </div>
      </div>
    );
  }

  // Show error state
  if (error) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md px-4">
            <h2 className="text-xl font-semibold text-destructive mb-2">
              Failed to Load Graph
            </h2>
            <p className="text-muted-foreground mb-4">
              {error instanceof Error
                ? error.message
                : 'An unexpected error occurred while loading the graph data. The repository may still be processing.'}
            </p>
            <Button onClick={() => navigate('/dashboard')}>
              <ArrowLeft className="h-4 w-4 mr-2" />
              Return to Dashboard
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background" role="application" aria-label="RepoLens Graph Explorer">
      <Header />

      <div className="border-b border-border p-3 flex items-center justify-between bg-gradient-to-r from-background to-background/95" role="toolbar" aria-label="Graph controls and actions">
        {/* Navigation group */}
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <div className="h-6 w-px bg-border" />
          <span className="font-semibold text-foreground">{repo?.name || repoId || 'Unknown Repository'}</span>
          {focusMode === 'neighbors' && selectedNode && (
            <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded-md">
              {nodes.length} of {graphNodes.length} nodes
            </span>
          )}
        </div>
        {/* Insights toggle — LEFT SIDE */}
        <div className="absolute top-[70px] left-[300px] z-20">
          <Button
            variant={showInsights ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowInsights(!showInsights)}
            className="h-8"
          >
            <Lightbulb className="h-4 w-4 mr-1.5" />
            Insights
          </Button>
        </div>

        <div className="flex items-center gap-2">
          {/* Search group */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <Input
              placeholder={searchMode === 'semantic' ? 'Describe the code...' : 'Search nodes...'}
              className="pl-9 w-56 h-9"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label={searchMode === 'semantic'
                ? 'Search the graph by meaning'
                : 'Search for files, classes, or functions in the graph'}
              role="searchbox"
            />
            {isSearching && (
              <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
            )}
            {!isSearching && searchQuery && highlightedNodes.size > 0 && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-primary-foreground bg-primary px-2 py-0.5 rounded-full font-medium" aria-label={`${highlightedNodes.size} results found`}>
                {highlightedNodes.size}
              </div>
            )}
          </div>

          {!isDemoMode && (
          <Button
            variant={searchMode === 'semantic' ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setSearchMode(searchMode === 'semantic' ? 'name' : 'semantic')}
            className="h-9"
            title="Search by meaning instead of by name"
            aria-pressed={searchMode === 'semantic'}
          >
            <Sparkles className="h-4 w-4 mr-1.5" />
            Semantic
          </Button>
          )}

          <div className="h-6 w-px bg-border" />

          {/* View controls group */}
          <div className="flex items-center bg-muted/50 rounded-lg p-1 gap-0.5" role="group" aria-label="View mode controls">
            <Button
              variant={viewMode === 'folder' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('folder')}
              title="Folder view"
              className="h-7 px-2"
              aria-label="Switch to folder view"
              aria-pressed={viewMode === 'folder'}
            >
              <FolderTree className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button
              variant={viewMode === 'flat' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('flat')}
              title="Flat view"
              className="h-7 px-2"
              aria-label="Switch to flat view"
              aria-pressed={viewMode === 'flat'}
            >
              <Network className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>

          {/* Folder controls group */}
          {viewMode === 'folder' && (
            <div className="flex items-center bg-muted/50 rounded-lg p-1 gap-0.5" role="group" aria-label="Folder expansion controls">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setCollapsedFolders(new Set(folderPathsRef))}
                title="Collapse all folders"
                className="h-7 px-2"
                aria-label="Collapse all folders in the graph"
              >
                <ChevronsDownUp className="h-4 w-4" aria-hidden="true" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setCollapsedFolders(new Set())}
                title="Expand all folders"
                className="h-7 px-2"
                aria-label="Expand all folders in the graph"
              >
                <ChevronsUpDown className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          )}

          {/* Active filter badge */}
          {filterFolder && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setFilterFolder(null)}
              title="Clear folder filter"
              className="gap-1 h-8"
            >
              <Filter className="h-3 w-3" />
              <span className="max-w-[100px] truncate">{filterFolder.split('/').pop()}</span>
              <X className="h-3 w-3" />
            </Button>
          )}

          {/* Layout direction */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setLayoutDirection(d => d === 'LR' ? 'TB' : 'LR')}
            title={layoutDirection === 'LR' ? 'Switch to vertical layout' : 'Switch to horizontal layout'}
            className="h-8"
            aria-label={layoutDirection === 'LR' ? 'Switch to vertical layout' : 'Switch to horizontal layout'}
          >
            {layoutDirection === 'LR' ? (
              <LayoutList className="h-4 w-4" aria-hidden="true" />
            ) : (
              <LayoutGrid className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>

          {/* Export Menu */}
          <ExportMenu
            containerRef={reactFlowWrapperRef}
            nodes={nodes}
            edges={edges}
          />

          <div className="h-6 w-px bg-border" />



          {/* Feature buttons group */}
          <div className="flex items-center gap-1.5" role="group" aria-label="Feature actions">
            <Button
              variant={chatOpen ? 'default' : 'outline'}
              size="sm"
              onClick={() => setChatOpen(!chatOpen)}
              className="h-8"
              aria-label={chatOpen ? 'Close AI chat panel' : 'Open AI chat panel'}
              aria-pressed={chatOpen}
            >
              <MessageSquare className="h-4 w-4 mr-1.5" aria-hidden="true" />
              AI Chat
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCommandPaletteOpen(true)}
              title="Open command palette (⌘K)"
              className="h-8 gap-1.5"
              aria-label="Open command palette. Keyboard shortcut: Command K"
            >
              <Command className="h-4 w-4" aria-hidden="true" />
              <kbd className="hidden sm:inline text-[10px] text-muted-foreground bg-muted px-1 rounded" aria-hidden="true">⌘K</kbd>
            </Button>
          </div>
        </div>
      </div>

      {/* Legend - positioned bottom-left with collapsible toggle */}
      <div className="absolute left-4 top-1/2 -translate-y-1/2 z-10">
        <div className="p-3 rounded-xl border-2 border-border bg-card/95 backdrop-blur-sm shadow-lg text-sm" role="region" aria-label="Graph legend">
          <button
            onClick={() => setLegendCollapsed(!legendCollapsed)}
            className="flex items-center justify-between w-full font-medium text-foreground mb-2 hover:text-primary transition-colors"
            aria-expanded={!legendCollapsed}
            aria-label={legendCollapsed ? 'Expand legend' : 'Collapse legend'}
          >
            <span>Legend</span>
            {legendCollapsed ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>

          {!legendCollapsed && (
            <div className="space-y-3 animate-fade-in-up">
              {/* Node Types */}
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1.5">Nodes</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-warning" />
                    <span className="text-muted-foreground text-xs">Folder</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-muted-foreground/60" />
                    <span className="text-muted-foreground text-xs">File</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-chart-1" />
                    <span className="text-muted-foreground text-xs">Class</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-chart-2" />
                    <span className="text-muted-foreground text-xs">Function</span>
                  </div>
                </div>
              </div>

              {/* Edge Types */}
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1.5">Edges</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  {Object.entries(edgeColors).map(([type, color]) => (
                    <div key={type} className="flex items-center gap-2">
                      <div className="w-4 h-0.5 rounded-full" style={{ backgroundColor: color }} />
                      <span className="capitalize text-muted-foreground text-xs">{type}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <ResizablePanelGroup direction="horizontal" className="flex-1">
        <ResizablePanel defaultSize={chatOpen ? 70 : 100} minSize={40}>
          <div className="h-full relative" ref={reactFlowWrapperRef} role="main" aria-label="Interactive code dependency graph">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              onPaneClick={onPaneClick}
              onNodeMouseEnter={onNodeMouseEnter}
              onNodeMouseLeave={onNodeMouseLeave}
              nodeTypes={nodeTypes}
              fitView
              className="bg-background touch-none"
              aria-label={`Graph showing ${nodes.length} nodes and ${edges.length} connections`}
              minZoom={0.1}
              maxZoom={2}
              defaultViewport={{ x: 0, y: 0, zoom: 1 }}
              attributionPosition="bottom-left"
              proOptions={{ hideAttribution: true }}
              panOnScroll
              zoomOnScroll
              zoomOnPinch
              panOnDrag
              preventScrolling
              elevateNodesOnSelect
              selectNodesOnDrag={false}
              // Touch optimizations
              panOnScrollSpeed={0.5}
              zoomActivationKeyCode={null}
            >
              <Controls
                className="!bg-card !border-border"
                showInteractive={false}
              />
              <MiniMap
                className="!bg-card !border-border"
                nodeColor={(node) => {
                  if (node.type === 'folder') return 'hsl(var(--warning))';
                  if (node.type === 'class') return 'hsl(var(--chart-1))';
                  if (node.type === 'function') return 'hsl(var(--chart-2))';
                  return 'hsl(var(--muted-foreground))';
                }}
                maskColor="hsl(var(--muted) / 0.3)"
                style={{ width: 200, height: 150 }}
              />
              <Background
                variant={BackgroundVariant.Dots}
                gap={20}
                size={1}
                color="hsl(var(--muted-foreground))"
                style={{ opacity: 0.3 }}
              />
            </ReactFlow>

            {/* Node Tooltip */}
            {hoveredNode && (
              <NodeTooltip
                id={hoveredNode.node.id}
                type={hoveredNode.node.type}
                name={hoveredNode.node.name}
                path={hoveredNode.node.path}
                summary={hoveredNode.node.summary}
                lineCount={hoveredNode.node.lineCount}
                language={(hoveredNode.node as any).language}
                childCount={hoveredNode.node.childCount}
                position={hoveredNode.position}
              />
            )}
          </div>
        </ResizablePanel>

        {chatOpen && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={30} minSize={20} maxSize={50}>
              <div className="h-full border-l border-border bg-background relative z-[60]">
                <ChatPanel
                  onClose={() => {
                    setChatOpen(false);
                    setChatNodeContext(null); // Clear chat context when closing
                  }}
                  nodeContext={chatNodeContext?.name}
                  nodeId={chatNodeContext?.id}
                  repoId={repoId}
                  repoName={repo?.name || repoId}
                  selectedNode={chatNodeContext}
                  totalNodes={graphNodes.length}
                  totalEdges={graphEdges.length}
                  autoSendQuestion={autoSendQuestion}
                  onQuestionSent={() => setAutoSendQuestion(false)}
                  onNodeClick={async (nodeId: string) => {
                    // Find the node in the graph
                    const node = nodes.find(n => n.id === nodeId);
                    if (node) {
                      // Simulate a click on that node
                      const mockEvent = {} as React.MouseEvent;
                      await onNodeClick(mockEvent, node);

                      // Center the view on the selected node
                      fitView({
                        nodes: [node],
                        padding: 0.3,
                        duration: 500
                      });
                    }
                  }}
                />
              </div>
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>

      {/* Insights Panel */}
      {showInsights && (
        <div className="absolute top-[140px] left-4 z-20 w-96 max-h-[calc(100vh-180px)] overflow-y-auto">
          <InsightsPanel
            insights={insightsData}
            isLoading={insightsLoading}
            onClose={() => setShowInsights(false)}
            onNodeClick={async (nodeId: string) => {
              const node = nodes.find(n => n.id === nodeId);
              if (node) {
                const mockEvent = {} as React.MouseEvent;
                await onNodeClick(mockEvent, node);
                fitView({
                  nodes: [node],
                  padding: 0.3,
                  duration: 500
                });
              }
            }}
          />
        </div>
      )}

      <NodeDrawer
        node={selectedNode}
        nodes={graphNodes}
        edges={graphEdges}
        onClose={() => {
          setSelectedNode(null);
          setHighlightedNodes(new Set());
        }}
        onAskAI={() => {
          // Save node context for chat before closing drawer
          setChatNodeContext(selectedNode);
          // Close the NodeDrawer when opening chat
          setSelectedNode(null);
          setHighlightedNodes(new Set());
          // Open chat panel with auto-send
          setChatOpen(true);
          setAutoSendQuestion(true);
        }}
        onFilterFolder={(folderPath) => {
          setFilterFolder(folderPath);
          setSelectedNode(null);
          setHighlightedNodes(new Set());
        }}
      />

      {/* Command Palette */}
      <CommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onNavigateToNode={async (nodeId: string) => {
          const node = nodes.find(n => n.id === nodeId);
          if (node) {
            const mockEvent = {} as React.MouseEvent;
            await onNodeClick(mockEvent, node);
            fitView({
              nodes: [node],
              padding: 0.3,
              duration: 500
            });
          }
        }}
        onApplyFilter={(filter: string) => {
          if (!filter) {
            setTypeFilter(null);
            setSearchQuery('');
            setHighlightedNodes(new Set());
          } else if (filter.startsWith('type=')) {
            const type = filter.replace('type=', '') as 'file' | 'class' | 'function';
            setTypeFilter(type);
          }
        }}
        onAskAI={(_question: string) => {
          // This will be handled by ChatPanel through the streaming hook
          setChatOpen(true);
        }}
        onOpenChat={() => setChatOpen(true)}
        nodes={graphNodes.map(n => ({
          id: n.id,
          name: n.name || n.id,
          type: n.type,
          path: n.path,
        }))}
      />

      {/* Help Center */}
      <HelpCenter
        open={helpCenterOpen}
        onClose={() => setHelpCenterOpen(false)}
      />

      {/* Screen reader announcements */}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {selectedNode && `Selected ${selectedNode.type}: ${selectedNode.name}`}
        {searchQuery && highlightedNodes.size > 0 && `Found ${highlightedNodes.size} results for ${searchQuery}`}
        {nodes.length > 0 && !searchQuery && !selectedNode && `Graph loaded with ${nodes.length} nodes`}
      </div>
    </div>
  );
}

// Wrapper component that provides ReactFlowProvider context
export default function GraphExplorer() {
  return (
    <ReactFlowProvider>
      <GraphExplorerInner />
    </ReactFlowProvider>
  );
}
