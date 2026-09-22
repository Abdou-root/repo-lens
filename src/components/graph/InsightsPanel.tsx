import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Lightbulb, TrendingUp, Network, Box, ChevronRight, Loader2, X, AlertTriangle, CheckCircle, Info, BarChart3 } from 'lucide-react';

interface Insight {
  id: string;
  name: string;
  type: string;
  path: string;
  reason: string;
  [key: string]: any;
}

interface InsightsData {
  repo_id: string;
  summary: {
    total_nodes: number;
    code_nodes: number;
    total_edges: number;
    avg_connections: number;
  };
  insights: {
    entry_points: Insight[];
    complexity_hotspots: Insight[];
    architecture_hubs: Insight[];
    isolated_modules: Insight[];
  };
}

interface InsightsPanelProps {
  insights: InsightsData | null;
  isLoading: boolean;
  onNodeClick: (nodeId: string) => void;
  onClose?: () => void;
}

export function InsightsPanel({ insights, isLoading, onNodeClick, onClose }: InsightsPanelProps) {
  const [expandedSection, setExpandedSection] = useState<string | null>('entry_points');

  // IMPORTANT: All hooks must be called before any conditional returns
  // to satisfy React's Rules of Hooks (same order on every render)

  // Memoize sections to avoid recreation on every render
  const sections = useMemo(() => {
    if (!insights) return [];
    return [
      {
        id: 'entry_points',
        title: 'Entry Points',
        description: 'Starting points with no incoming dependencies',
        icon: TrendingUp,
        data: insights.insights.entry_points,
        color: 'text-green-500'
      },
      {
        id: 'complexity_hotspots',
        title: 'Complexity Hotspots',
        description: 'Highly connected nodes that may need attention',
        icon: Network,
        data: insights.insights.complexity_hotspots,
        color: 'text-orange-500'
      },
      {
        id: 'architecture_hubs',
        title: 'Architecture Hubs',
        description: 'Central coordination points in your codebase',
        icon: Box,
        data: insights.insights.architecture_hubs,
        color: 'text-blue-500'
      },
      {
        id: 'isolated_modules',
        title: 'Isolated Modules',
        description: 'Weakly connected components',
        icon: Box,
        data: insights.insights.isolated_modules,
        color: 'text-gray-500'
      }
    ];
  }, [insights]);

  // Memoize health metrics calculation
  const { complexityScore, modularityScore, overallHealth } = useMemo(() => {
    if (!insights) return { complexityScore: 0, modularityScore: 0, overallHealth: 0 };
    const complexity = Math.max(0, 100 - (insights.insights.complexity_hotspots.length * 10));
    const modularity = Math.min(100, insights.insights.isolated_modules.length * 20);
    return {
      complexityScore: complexity,
      modularityScore: modularity,
      overallHealth: Math.round((complexity + modularity) / 2)
    };
  }, [insights]);

  // Early returns AFTER all hooks have been called
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="h-5 w-5" />
              Codebase Insights
            </CardTitle>
            {onClose && (
              <Button variant="ghost" size="sm" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!insights) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="h-5 w-5" />
              Codebase Insights
            </CardTitle>
            <CardDescription>
              {insights.summary.code_nodes} code nodes, {insights.summary.total_edges} connections
              (avg {insights.summary.avg_connections.toFixed(1)} per node)
            </CardDescription>
          </div>
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Health Overview */}
        <div className="p-3 border rounded-lg bg-muted/30">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium">Codebase Health</span>
            </div>
            <Badge variant={overallHealth >= 70 ? 'default' : overallHealth >= 40 ? 'secondary' : 'destructive'}>
              {overallHealth}%
            </Badge>
          </div>
          <Progress value={overallHealth} className="h-2 mb-3" />

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="space-y-1">
              <div className="flex items-center gap-1 text-muted-foreground">
                {complexityScore >= 70 ? (
                  <CheckCircle className="h-3 w-3 text-green-500" />
                ) : complexityScore >= 40 ? (
                  <Info className="h-3 w-3 text-yellow-500" />
                ) : (
                  <AlertTriangle className="h-3 w-3 text-red-500" />
                )}
                <span>Complexity</span>
              </div>
              <Progress value={complexityScore} className="h-1.5" />
              <p className="text-[10px] text-muted-foreground">
                {insights.insights.complexity_hotspots.length} hotspot{insights.insights.complexity_hotspots.length !== 1 ? 's' : ''}
              </p>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-1 text-muted-foreground">
                {modularityScore >= 70 ? (
                  <CheckCircle className="h-3 w-3 text-green-500" />
                ) : modularityScore >= 40 ? (
                  <Info className="h-3 w-3 text-yellow-500" />
                ) : (
                  <AlertTriangle className="h-3 w-3 text-red-500" />
                )}
                <span>Modularity</span>
              </div>
              <Progress value={modularityScore} className="h-1.5" />
              <p className="text-[10px] text-muted-foreground">
                {insights.insights.isolated_modules.length} module{insights.insights.isolated_modules.length !== 1 ? 's' : ''}
              </p>
            </div>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-3 gap-2">
          <div className="p-2 border rounded-lg text-center">
            <div className="text-2xl font-bold text-green-600">
              {insights.insights.entry_points.length}
            </div>
            <div className="text-[10px] text-muted-foreground">Entry Points</div>
          </div>
          <div className="p-2 border rounded-lg text-center">
            <div className="text-2xl font-bold text-orange-600">
              {insights.insights.complexity_hotspots.length}
            </div>
            <div className="text-[10px] text-muted-foreground">Hotspots</div>
          </div>
          <div className="p-2 border rounded-lg text-center">
            <div className="text-2xl font-bold text-blue-600">
              {insights.insights.architecture_hubs.length}
            </div>
            <div className="text-[10px] text-muted-foreground">Hubs</div>
          </div>
        </div>
        {sections.map((section) => {
          const Icon = section.icon;
          const isExpanded = expandedSection === section.id;
          const hasData = section.data.length > 0;

          return (
            <div key={section.id} className="border rounded-lg">
              <button
                onClick={() => setExpandedSection(isExpanded ? null : section.id)}
                className="w-full px-3 py-2 flex items-center justify-between hover:bg-muted/50 transition-colors rounded-lg"
              >
                <div className="flex items-center gap-2">
                  <Icon className={`h-4 w-4 ${section.color}`} />
                  <div className="text-left">
                    <p className="text-sm font-medium">{section.title}</p>
                    <p className="text-xs text-muted-foreground">{section.description}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="text-xs">
                    {section.data.length}
                  </Badge>
                  <ChevronRight
                    className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                  />
                </div>
              </button>

              {isExpanded && (
                <div className="px-3 pb-3 space-y-2">
                  {hasData ? (
                    section.data.map((item) => (
                      <button
                        key={item.id}
                        onClick={() => onNodeClick(item.id)}
                        className="w-full p-2 text-left border rounded hover:bg-muted/50 transition-colors group"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate group-hover:text-primary">
                              {item.name}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                              {item.path}
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              {item.reason}
                            </p>
                          </div>
                          <Badge variant="outline" className="text-xs capitalize shrink-0">
                            {item.type}
                          </Badge>
                        </div>
                      </button>
                    ))
                  ) : (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No items found
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
