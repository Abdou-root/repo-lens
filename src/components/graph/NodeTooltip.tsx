import { memo } from 'react';
import { FileText, Box, Zap, Folder, Code2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface NodeTooltipProps {
  id: string;
  type: 'file' | 'class' | 'function' | 'folder';
  name: string;
  path?: string;
  summary?: string;
  lineCount?: number;
  language?: string;
  childCount?: number;
  position: { x: number; y: number };
}

export const NodeTooltip = memo(({ type, name, path, summary, lineCount, language, childCount, position }: NodeTooltipProps) => {
  const getIcon = () => {
    switch (type) {
      case 'folder':
        return <Folder className="h-4 w-4 text-warning" />;
      case 'class':
        return <Box className="h-4 w-4 text-chart-1" />;
      case 'function':
        return <Zap className="h-4 w-4 text-chart-2" />;
      default:
        return <FileText className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getTypeColor = () => {
    switch (type) {
      case 'folder':
        return 'border-warning/50 bg-warning/5';
      case 'class':
        return 'border-chart-1/50 bg-chart-1/5';
      case 'function':
        return 'border-chart-2/50 bg-chart-2/5';
      default:
        return 'border-border bg-card';
    }
  };

  return (
    <div
      className={cn(
        'absolute z-[1000] pointer-events-none',
        'max-w-xs p-3 rounded-lg border-2 shadow-xl',
        'bg-card/95 backdrop-blur-sm',
        getTypeColor()
      )}
      style={{
        left: position.x + 20,
        top: position.y - 10,
      }}
    >
      <div className="space-y-2">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-border pb-2">
          <div className="p-1.5 rounded-lg bg-muted/50">
            {getIcon()}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-mono text-sm font-semibold truncate">{name}</p>
            <p className="text-xs text-muted-foreground capitalize">{type}</p>
          </div>
        </div>

        {/* Path */}
        {path && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Path:</p>
            <p className="text-xs font-mono text-foreground/80 break-all">{path}</p>
          </div>
        )}

        {/* Metadata */}
        {(lineCount || language || childCount !== undefined) && (
          <div className="flex items-center gap-3 text-xs pt-1">
            {lineCount && (
              <span className="flex items-center gap-1 text-muted-foreground">
                <Code2 className="h-3 w-3" />
                {lineCount} lines
              </span>
            )}
            {language && (
              <span className="px-2 py-0.5 rounded bg-primary/10 font-medium text-primary">
                {language}
              </span>
            )}
            {childCount !== undefined && type === 'folder' && (
              <span className="text-muted-foreground">
                {childCount} {childCount === 1 ? 'item' : 'items'}
              </span>
            )}
          </div>
        )}

        {/* Summary */}
        {summary && (
          <div className="space-y-1 pt-1 border-t border-border">
            <p className="text-xs font-medium text-muted-foreground">Summary:</p>
            <p className="text-xs text-foreground/70 line-clamp-3">{summary}</p>
          </div>
        )}

        {/* Tooltip arrow */}
        <div
          className="absolute w-2 h-2 bg-card border-l-2 border-t-2 border-border rotate-45"
          style={{
            left: -5,
            top: 20,
          }}
        />
      </div>
    </div>
  );
});

NodeTooltip.displayName = 'NodeTooltip';
