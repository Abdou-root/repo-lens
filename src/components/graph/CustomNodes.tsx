import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { FileText, Box, Zap, Folder, ChevronDown, ChevronRight, Code2, FileCode } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CustomNodeData {
  name: string;
  path: string;
  summary?: string;
  highlighted?: boolean;
  similarity?: number;
  lineCount?: number;
  language?: string;
}

interface FolderNodeData extends CustomNodeData {
  childCount?: number;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const FileNode = memo(({ data, selected }: { data: CustomNodeData; selected?: boolean }) => {
  const getFileIcon = () => {
    const ext = data.name.split('.').pop()?.toLowerCase();
    if (['ts', 'tsx', 'js', 'jsx'].includes(ext || '')) return FileCode;
    return FileText;
  };

  const FileIcon = getFileIcon();
  const opacity = data.similarity ? Math.max(0.5, data.similarity) : (data.highlighted ? 1 : 0.5);

  return (
    <div
      className={cn(
        'px-4 py-3 rounded-xl border bg-white dark:bg-gradient-to-br dark:from-card dark:to-card/90 shadow-md transition-all duration-200 hover:shadow-xl hover:border-primary/50 hover:scale-[1.03] min-w-[180px] max-w-[280px]',
        selected ? 'border-primary shadow-xl shadow-primary/30 ring-4 ring-primary/30 scale-105' : 'border-border',
        data.highlighted && 'ring-4 ring-blue-500 dark:ring-blue-400 border-blue-500 dark:border-blue-400 shadow-xl shadow-blue-500/30',
        !data.highlighted && !data.similarity && 'saturate-50'
      )}
      style={{ opacity }}
    >
      <Handle type="target" position={Position.Left} className="!bg-foreground/60 !w-3 !h-3" />
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-muted/50 transition-colors group-hover:bg-primary/10">
            <FileIcon className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="flex-1 min-w-0">
            <span className="font-mono text-sm font-medium truncate block">{data.name}</span>
          </div>
        </div>
        {(data.lineCount || data.language || data.summary) && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground pl-8">
            {data.lineCount && (
              <span className="flex items-center gap-1">
                <Code2 className="h-3 w-3" />
                {data.lineCount} lines
              </span>
            )}
            {data.language && (
              <span className="px-1.5 py-0.5 rounded bg-muted/50 font-medium">
                {data.language}
              </span>
            )}
          </div>
        )}
        {data.summary && (
          <p className="text-xs text-muted-foreground pl-8 line-clamp-2">{data.summary}</p>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-foreground/60 !w-3 !h-3" />
    </div>
  );
});

FileNode.displayName = 'FileNode';

export const ClassNode = memo(({ data, selected }: { data: CustomNodeData; selected?: boolean }) => {
  const opacity = data.similarity ? Math.max(0.5, data.similarity) : (data.highlighted ? 1 : 0.5);

  return (
    <div
      className={cn(
        'px-4 py-3 rounded-xl border-2 bg-white dark:bg-gradient-to-br dark:from-card dark:to-card/90 shadow-md transition-all duration-200 hover:shadow-xl hover:border-chart-1/50 hover:scale-[1.03] min-w-[200px] max-w-[300px]',
        selected ? 'border-chart-1 shadow-xl shadow-chart-1/30 ring-4 ring-chart-1/30 scale-105' : 'border-chart-1/30',
        data.highlighted && 'ring-4 ring-blue-500 dark:ring-blue-400 border-blue-500 dark:border-blue-400 shadow-xl shadow-blue-500/30',
        !data.highlighted && !data.similarity && 'saturate-50'
      )}
      style={{ opacity }}
    >
      <Handle type="target" position={Position.Left} className="!bg-chart-1 !w-3 !h-3" />
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-chart-1/20 transition-all group-hover:bg-chart-1/30">
            <Box className="h-5 w-5 text-chart-1" />
          </div>
          <div className="flex-1 min-w-0">
            <span className="font-mono text-sm font-bold truncate block text-chart-1">{data.name}</span>
          </div>
        </div>
        {(data.lineCount || data.language) && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground pl-10">
            {data.lineCount && (
              <span className="flex items-center gap-1">
                <Code2 className="h-3 w-3" />
                {data.lineCount} lines
              </span>
            )}
            {data.language && (
              <span className="px-1.5 py-0.5 rounded bg-chart-1/10 font-medium text-chart-1">
                {data.language}
              </span>
            )}
          </div>
        )}
        {data.summary && (
          <p className="text-xs text-muted-foreground pl-10 line-clamp-2">{data.summary}</p>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-chart-1 !w-3 !h-3" />
    </div>
  );
});

ClassNode.displayName = 'ClassNode';

export const FunctionNode = memo(({ data, selected }: { data: CustomNodeData; selected?: boolean }) => {
  const opacity = data.similarity ? Math.max(0.5, data.similarity) : (data.highlighted ? 1 : 0.5);

  return (
    <div
      className={cn(
        'px-4 py-3 rounded-xl border bg-white dark:bg-gradient-to-br dark:from-card dark:to-card/90 shadow-md transition-all duration-200 hover:shadow-xl hover:border-chart-2/50 hover:scale-[1.03] min-w-[180px] max-w-[280px]',
        selected ? 'border-chart-2 shadow-xl shadow-chart-2/30 ring-4 ring-chart-2/30 scale-105' : 'border-chart-2/20',
        data.highlighted && 'ring-4 ring-blue-500 dark:ring-blue-400 border-blue-500 dark:border-blue-400 shadow-xl shadow-blue-500/30',
        !data.highlighted && !data.similarity && 'saturate-50'
      )}
      style={{ opacity }}
    >
      <Handle type="target" position={Position.Left} className="!bg-chart-2 !w-3 !h-3" />
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-chart-2/20 transition-all group-hover:bg-chart-2/30">
            <Zap className="h-4 w-4 text-chart-2" />
          </div>
          <div className="flex-1 min-w-0">
            <span className="font-mono text-sm font-semibold truncate block text-chart-2">{data.name}</span>
          </div>
        </div>
        {(data.lineCount || data.language) && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground pl-8">
            {data.lineCount && (
              <span className="flex items-center gap-1">
                <Code2 className="h-3 w-3" />
                {data.lineCount} lines
              </span>
            )}
            {data.language && (
              <span className="px-1.5 py-0.5 rounded bg-chart-2/10 font-medium text-chart-2">
                {data.language}
              </span>
            )}
          </div>
        )}
        {data.summary && (
          <p className="text-xs text-muted-foreground pl-8 line-clamp-2">{data.summary}</p>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-chart-2 !w-3 !h-3" />
    </div>
  );
});

FunctionNode.displayName = 'FunctionNode';

export const FolderNode = memo(({ data, selected }: { data: FolderNodeData; selected?: boolean }) => {
  const ChevronIcon = data.isCollapsed ? ChevronRight : ChevronDown;
  const opacity = data.similarity ? Math.max(0.5, data.similarity) : (data.highlighted ? 1 : 0.5);

  return (
    <div
      className={cn(
        'px-4 py-3 rounded-xl border-2 bg-white dark:bg-gradient-to-br dark:from-amber-500/10 dark:to-amber-500/5 shadow-md transition-all duration-200 min-w-[200px] max-w-[320px] hover:shadow-xl hover:scale-[1.03]',
        selected
          ? 'border-amber-500 shadow-xl shadow-amber-500/30 ring-4 ring-amber-500/30 scale-105 bg-amber-50 dark:bg-amber-500/20'
          : 'border-border/60 hover:border-amber-500/50',
        !data.highlighted && !data.similarity && 'saturate-50'
      )}
      style={{ opacity }}
    >
      <Handle type="target" position={Position.Left} className="!bg-transparent !border-0 !w-0 !h-0 !min-w-0 !min-h-0 !opacity-0 !pointer-events-none" />
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              data.onToggleCollapse?.();
            }}
            className="p-1 hover:bg-amber-500/20 rounded-lg transition-colors flex-shrink-0"
            title={data.isCollapsed ? 'Expand folder' : 'Collapse folder'}
          >
            <ChevronIcon className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          </button>
          <div className="relative p-2 rounded-lg bg-amber-500/20 flex-shrink-0">
            <Folder className="h-5 w-5 text-amber-600 dark:text-amber-400" />
            {data.childCount !== undefined && data.childCount > 0 && (
              <span className="absolute -top-2 -right-2 min-w-[18px] h-5 flex items-center justify-center bg-amber-500 text-white text-[10px] font-bold rounded-full px-1.5 shadow-md">
                {data.childCount > 99 ? '99+' : data.childCount}
              </span>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <span className="font-mono text-sm font-bold truncate block text-amber-700 dark:text-amber-300">{data.name}</span>
            {data.childCount !== undefined && data.childCount > 0 && (
              <span className="text-xs text-muted-foreground">
                {data.childCount} {data.childCount === 1 ? 'item' : 'items'}
              </span>
            )}
          </div>
        </div>
        {data.summary && (
          <p className="text-xs text-muted-foreground pl-12 line-clamp-1">{data.summary}</p>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-transparent !border-0 !w-0 !h-0 !min-w-0 !min-h-0 !opacity-0 !pointer-events-none" />
    </div>
  );
});

FolderNode.displayName = 'FolderNode';
