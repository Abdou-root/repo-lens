import { GraphNode, GraphEdge } from '@/types';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { FileText, Box, Zap, MessageSquare, ArrowDownLeft, ArrowUpRight, Package, GitBranch, AlertCircle, CheckCircle, Folder, Filter, Copy, Check } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { getFolderPath, getLanguageFromPath } from '@/lib/graph-utils';
import { EDGE_COLORS_HEX, EDGE_TYPE_LABELS } from '@/lib/graph-constants';

// Use shared constants
const edgeTypeColors = EDGE_COLORS_HEX;
const edgeTypeLabels = EDGE_TYPE_LABELS;

interface NodeDrawerProps {
  node: GraphNode | null;
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  onClose: () => void;
  onAskAI: () => void;
  onFilterFolder?: (folderPath: string) => void;
}

interface DependencyWithEdge {
  node: GraphNode | null;
  edge: GraphEdge;
  isExternal: boolean;
}

export function NodeDrawer({ node, nodes = [], edges = [], onClose, onAskAI, onFilterFolder }: NodeDrawerProps) {
  const [copied, setCopied] = useState(false);

  if (!node) return null;

  const isFolder = node.type === 'folder';
  const language = node.path ? getLanguageFromPath(node.path) : 'text';

  const handleCopyCode = async () => {
    if (node.code) {
      await navigator.clipboard.writeText(node.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // For folders, calculate stats about contents
  const folderStats = isFolder ? (() => {
    const nodesInFolder = nodes.filter(n =>
      n.path && getFolderPath(n.path) === node.path
    );
    const fileCount = nodesInFolder.filter(n => n.type.toLowerCase() === 'file').length;
    const classCount = nodesInFolder.filter(n => n.type.toLowerCase() === 'class').length;
    const functionCount = nodesInFolder.filter(n => n.type.toLowerCase() === 'function').length;
    const totalLines = nodesInFolder.reduce((sum, n) => sum + (n.lineCount || 0), 0);

    // Get external packages used by files in this folder
    const filesInFolder = new Set(nodesInFolder.map(n => n.id));
    const externalDeps = new Set<string>();
    edges.forEach(edge => {
      if (filesInFolder.has(edge.source) && edge.type === 'external') {
        externalDeps.add(edge.target);
      }
    });

    return { fileCount, classCount, functionCount, totalLines, externalDeps: Array.from(externalDeps), nodesInFolder };
  })() : null;

  // Calculate incoming and outgoing dependencies with edge type info
  const incomingEdges = edges.filter(edge => edge.target === node.id);
  const outgoingEdges = edges.filter(edge => edge.source === node.id);

  // Group outgoing edges by type
  const internalOutgoing: DependencyWithEdge[] = [];
  const externalOutgoing: DependencyWithEdge[] = [];

  outgoingEdges.forEach(edge => {
    const targetNode = nodes.find(n => n.id === edge.target) || null;
    const isExternal = edge.type === 'external';
    const dep: DependencyWithEdge = { node: targetNode, edge, isExternal };
    if (isExternal) {
      externalOutgoing.push(dep);
    } else {
      internalOutgoing.push(dep);
    }
  });

  const incomingDeps = incomingEdges
    .map(edge => ({
      node: nodes.find(n => n.id === edge.source) || null,
      edge,
      isExternal: edge.type === 'external',
    }))
    .filter((dep): dep is DependencyWithEdge => dep.node !== null);

  const icons: Record<string, typeof FileText> = {
    file: FileText,
    class: Box,
    function: Zap,
    folder: Folder,
  };

  // Use FileText as fallback for unknown node types to prevent crash
  const Icon = icons[node.type] || FileText;

  return (
    <Sheet open={!!node} onOpenChange={(open) => !open && onClose()}>
      <SheetContent size="lg" className="flex flex-col z-[45] [&~div]:z-[45]">
        <SheetHeader>
          <div className="flex items-center gap-2">
            <Icon className="h-5 w-5 text-primary" />
            <SheetTitle className="font-mono">{node.name}</SheetTitle>
          </div>
          <SheetDescription className="font-mono text-xs">
            {node.path}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-200px)] mt-6">
          <div className="space-y-6">
            {/* Folder Stats - only for folder nodes */}
            {isFolder && folderStats && (
              <section>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <Folder className="h-4 w-4 text-yellow-500" />
                  Folder Contents
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-muted/30">
                    <p className="text-xs text-muted-foreground">Files</p>
                    <p className="font-medium">{folderStats.fileCount}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/30">
                    <p className="text-xs text-muted-foreground">Classes</p>
                    <p className="font-medium">{folderStats.classCount}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/30">
                    <p className="text-xs text-muted-foreground">Functions</p>
                    <p className="font-medium">{folderStats.functionCount}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/30">
                    <p className="text-xs text-muted-foreground">Total Lines</p>
                    <p className="font-medium">{folderStats.totalLines || 'N/A'}</p>
                  </div>
                </div>

                {/* External packages used in this folder */}
                {folderStats.externalDeps.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs text-muted-foreground mb-2">External packages used:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {folderStats.externalDeps.slice(0, 10).map((dep) => (
                        <span
                          key={dep}
                          className="text-xs font-mono px-2 py-1 rounded bg-muted/50 text-muted-foreground"
                        >
                          {dep}
                        </span>
                      ))}
                      {folderStats.externalDeps.length > 10 && (
                        <span className="text-xs text-muted-foreground">
                          +{folderStats.externalDeps.length - 10} more
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* Filter to folder button */}
                {onFilterFolder && node.path && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full mt-3"
                    onClick={() => onFilterFolder(node.path!)}
                  >
                    <Filter className="h-4 w-4 mr-2" />
                    Filter graph to this folder
                  </Button>
                )}
              </section>
            )}

            {/* AI Summary */}
            <section>
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <MessageSquare className="h-4 w-4" />
                AI Summary
              </h3>
              <p className="text-sm text-muted-foreground bg-muted/30 p-3 rounded-lg">
                {node.summary || 'No summary available. Click "Ask AI" to generate one.'}
              </p>
            </section>

            {/* Code Preview with Syntax Highlighting */}
            {node.code && (
              <section>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold">Code Preview</h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={handleCopyCode}
                  >
                    {copied ? (
                      <>
                        <Check className="h-3 w-3 mr-1 text-success" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3 mr-1" />
                        Copy
                      </>
                    )}
                  </Button>
                </div>
                <div className="rounded-lg overflow-hidden border border-border">
                  <SyntaxHighlighter
                    language={language}
                    style={oneDark}
                    customStyle={{
                      margin: 0,
                      padding: '1rem',
                      fontSize: '0.75rem',
                      borderRadius: '0.5rem',
                      maxHeight: '300px',
                    }}
                    showLineNumbers
                    wrapLines
                  >
                    {node.code}
                  </SyntaxHighlighter>
                </div>
              </section>
            )}

            {/* Stats */}
            <section>
              <h3 className="text-sm font-semibold mb-2">Details</h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">Type</p>
                  <p className="font-medium capitalize">{node.type}</p>
                </div>
                {node.lineCount !== undefined && (
                  <div className="p-3 rounded-lg bg-muted/30">
                    <p className="text-xs text-muted-foreground">Lines</p>
                    <p className="font-medium">{node.lineCount}</p>
                  </div>
                )}
                <div className="p-3 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">Incoming</p>
                  <p className="font-medium">{incomingDeps.length}</p>
                </div>
                <div className="p-3 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">Outgoing</p>
                  <p className="font-medium">{internalOutgoing.length + externalOutgoing.length}</p>
                </div>
              </div>
            </section>

            {/* Code Insights */}
            <section>
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <GitBranch className="h-4 w-4" />
                Code Insights
              </h3>
              <div className="flex flex-wrap gap-2">
                {/* Complexity indicators based on dependencies */}
                {(internalOutgoing.length + externalOutgoing.length) > 10 ? (
                  <Badge variant="destructive" className="text-xs">
                    <AlertCircle className="h-3 w-3 mr-1" />
                    High coupling ({internalOutgoing.length + externalOutgoing.length} deps)
                  </Badge>
                ) : (internalOutgoing.length + externalOutgoing.length) <= 3 ? (
                  <Badge variant="secondary" className="text-xs bg-green-500/10 text-green-600 hover:bg-green-500/20">
                    <CheckCircle className="h-3 w-3 mr-1" />
                    Low coupling
                  </Badge>
                ) : (
                  <Badge variant="secondary" className="text-xs">
                    Moderate coupling
                  </Badge>
                )}

                {/* File size indicator */}
                {node.lineCount !== undefined && (
                  node.lineCount > 300 ? (
                    <Badge variant="destructive" className="text-xs">
                      <AlertCircle className="h-3 w-3 mr-1" />
                      Large file ({node.lineCount} lines)
                    </Badge>
                  ) : node.lineCount < 50 ? (
                    <Badge variant="secondary" className="text-xs bg-green-500/10 text-green-600 hover:bg-green-500/20">
                      Small file
                    </Badge>
                  ) : null
                )}

                {/* Incoming dependencies indicator */}
                {incomingDeps.length > 5 && (
                  <Badge variant="outline" className="text-xs">
                    High usage ({incomingDeps.length} dependents)
                  </Badge>
                )}

                {/* External dependencies */}
                {externalOutgoing.length > 0 && (
                  <Badge variant="outline" className="text-xs">
                    {externalOutgoing.length} external dep{externalOutgoing.length !== 1 ? 's' : ''}
                  </Badge>
                )}

                {/* Entry point indicator (no incoming, has outgoing) */}
                {incomingDeps.length === 0 && (internalOutgoing.length + externalOutgoing.length) > 0 && (
                  <Badge variant="secondary" className="text-xs bg-blue-500/10 text-blue-600 hover:bg-blue-500/20">
                    Entry point
                  </Badge>
                )}

                {/* Leaf node indicator (has incoming, no outgoing) */}
                {incomingDeps.length > 0 && internalOutgoing.length === 0 && externalOutgoing.length === 0 && (
                  <Badge variant="secondary" className="text-xs">
                    Leaf node
                  </Badge>
                )}
              </div>
            </section>

            {/* Incoming Dependencies */}
            <section>
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <ArrowDownLeft className="h-4 w-4" />
                Incoming Dependencies ({incomingDeps.length})
              </h3>
              {incomingDeps.length > 0 ? (
                <div className="space-y-1">
                  {incomingDeps.map((dep) => (
                    <div
                      key={dep.edge.id}
                      className="text-sm p-2 rounded border border-border hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium font-mono text-xs">{dep.node?.name}</span>
                        <span
                          className="text-xs px-1.5 py-0.5 rounded"
                          style={{
                            backgroundColor: `${edgeTypeColors[dep.edge.type]}20`,
                            color: edgeTypeColors[dep.edge.type]
                          }}
                        >
                          {edgeTypeLabels[dep.edge.type] || dep.edge.type}
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground capitalize">{dep.node?.type}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground bg-muted/30 p-3 rounded-lg">
                  No incoming dependencies
                </div>
              )}
            </section>

            {/* Internal Dependencies (imports, calls, inherits) */}
            <section>
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <ArrowUpRight className="h-4 w-4" />
                Internal Dependencies ({internalOutgoing.length})
              </h3>
              {internalOutgoing.length > 0 ? (
                <div className="space-y-1">
                  {internalOutgoing.map((dep) => (
                    <div
                      key={dep.edge.id}
                      className="text-sm p-2 rounded border border-border hover:bg-muted/50 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium font-mono text-xs">
                          {dep.node?.name || dep.edge.target}
                        </span>
                        <span
                          className="text-xs px-1.5 py-0.5 rounded"
                          style={{
                            backgroundColor: `${edgeTypeColors[dep.edge.type]}20`,
                            color: edgeTypeColors[dep.edge.type]
                          }}
                        >
                          {edgeTypeLabels[dep.edge.type] || dep.edge.type}
                        </span>
                      </div>
                      {dep.node && (
                        <div className="text-xs text-muted-foreground capitalize">{dep.node.type}</div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground bg-muted/30 p-3 rounded-lg">
                  No internal dependencies
                </div>
              )}
            </section>

            {/* External Packages (npm, pip) */}
            {externalOutgoing.length > 0 && (
              <section>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <Package className="h-4 w-4" />
                  External Packages ({externalOutgoing.length})
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {externalOutgoing.map((dep) => (
                    <span
                      key={dep.edge.id}
                      className="text-xs font-mono px-2 py-1 rounded bg-muted/50 text-muted-foreground"
                    >
                      {dep.edge.target}
                    </span>
                  ))}
                </div>
              </section>
            )}
          </div>
        </ScrollArea>

        {/* Sticky footer with Ask AI button */}
        <div className="mt-auto pt-4 border-t border-border bg-background -mx-6 px-6 pb-0">
          <Button className="w-full" onClick={onAskAI}>
            <MessageSquare className="h-4 w-4 mr-2" />
            Ask AI about this {node.type}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
