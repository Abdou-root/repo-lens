/**
 * Shared constants for graph visualization components.
 *
 * Centralizes edge colors, type labels, and layout configuration
 * to ensure consistency across GraphExplorer, NodeDrawer, and exports.
 */

/**
 * Theme-aware edge colors using CSS variables.
 * Used in GraphExplorer for rendering edges.
 */
export const EDGE_COLORS: Record<string, string> = {
  imports: 'hsl(var(--chart-2))',     // Blue - internal imports
  calls: 'hsl(var(--chart-3))',       // Green - function calls
  inherits: 'hsl(var(--chart-4))',    // Purple - class inheritance
  external: 'hsl(var(--chart-5))',    // Gray - external packages
  defines: 'hsl(var(--muted-foreground))', // Muted gray - file defines
};

/**
 * Hex colors for contexts that don't support CSS variables.
 * Used in exports (PNG, SVG) and NodeDrawer badges.
 */
export const EDGE_COLORS_HEX: Record<string, string> = {
  imports: '#60A5FA',   // Blue
  calls: '#4ADE80',     // Green
  inherits: '#A78BFA',  // Purple
  external: '#6B7280',  // Gray
  defines: '#9CA3AF',   // Light gray
};

/**
 * Human-readable labels for edge types.
 */
export const EDGE_TYPE_LABELS: Record<string, string> = {
  imports: 'imports',
  calls: 'calls',
  inherits: 'inherits',
  external: 'external pkg',
  defines: 'defines',
};

/**
 * Layout configuration for Dagre graph layout.
 * Matches actual rendered node dimensions to prevent overlapping.
 */
export const LAYOUT_CONFIG = {
  nodeSep: 80,           // Spacing between nodes
  rankSep: 150,          // Vertical spacing between ranks/levels
  nodeWidth: 320,        // Max width + padding (280px + ~40px)
  nodeHeight: 140,       // Height for multi-line content, summaries, badges
  folderWidth: 360,      // Max width + padding (320px + ~40px)
  folderHeight: 100,     // Height for folder content with summary
};

/**
 * Node type configuration for React Flow.
 */
export const NODE_TYPES = ['file', 'class', 'function', 'folder'] as const;
export type NodeType = typeof NODE_TYPES[number];

/**
 * Get color for an edge type (hex version for exports).
 */
export function getEdgeColorHex(edgeType: string): string {
  return EDGE_COLORS_HEX[edgeType] || EDGE_COLORS_HEX.external;
}

/**
 * Get color for an edge type (CSS variable version).
 */
export function getEdgeColor(edgeType: string): string {
  return EDGE_COLORS[edgeType] || EDGE_COLORS.external;
}

/**
 * Get label for an edge type.
 */
export function getEdgeTypeLabel(edgeType: string): string {
  return EDGE_TYPE_LABELS[edgeType] || edgeType;
}
