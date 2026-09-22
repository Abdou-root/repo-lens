import { useState, useEffect, useCallback, useRef } from 'react';
import { Zap, Filter, MessageSquare, FileText, Box, Folder, Command, CornerDownLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  icon?: React.ReactNode;
  shortcut?: string;
  action: () => void;
  category: 'command' | 'node' | 'filter';
}

interface NodeItem {
  id: string;
  name: string;
  type: string;
  path?: string;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onNavigateToNode: (nodeId: string) => void;
  onApplyFilter: (filter: string) => void;
  onAskAI: (question: string) => void;
  onOpenChat: () => void;
  nodes: NodeItem[];
}

// Get icon for node type
function getNodeIcon(type: string) {
  switch (type.toLowerCase()) {
    case 'function':
      return <Zap className="h-4 w-4 text-chart-2" />;
    case 'class':
      return <Box className="h-4 w-4 text-chart-1" />;
    case 'folder':
      return <Folder className="h-4 w-4 text-yellow-500" />;
    default:
      return <FileText className="h-4 w-4 text-muted-foreground" />;
  }
}

export function CommandPalette({
  open,
  onClose,
  onNavigateToNode,
  onApplyFilter,
  onAskAI,
  onOpenChat,
  nodes
}: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Build command list
  const commands: CommandItem[] = [
    {
      id: 'cmd-chat',
      label: 'Open AI Chat',
      description: 'Ask questions about the codebase',
      icon: <MessageSquare className="h-4 w-4" />,
      shortcut: '⌘+Shift+C',
      action: () => { onOpenChat(); onClose(); },
      category: 'command',
    },
    {
      id: 'cmd-filter-functions',
      label: 'Filter: Functions only',
      description: 'Show only function nodes',
      icon: <Filter className="h-4 w-4" />,
      action: () => { onApplyFilter('type=function'); onClose(); },
      category: 'filter',
    },
    {
      id: 'cmd-filter-classes',
      label: 'Filter: Classes only',
      description: 'Show only class nodes',
      icon: <Filter className="h-4 w-4" />,
      action: () => { onApplyFilter('type=class'); onClose(); },
      category: 'filter',
    },
    {
      id: 'cmd-filter-files',
      label: 'Filter: Files only',
      description: 'Show only file nodes',
      icon: <Filter className="h-4 w-4" />,
      action: () => { onApplyFilter('type=file'); onClose(); },
      category: 'filter',
    },
    {
      id: 'cmd-clear-filter',
      label: 'Clear all filters',
      description: 'Show all nodes',
      icon: <Filter className="h-4 w-4" />,
      action: () => { onApplyFilter(''); onClose(); },
      category: 'filter',
    },
  ];

  // Check if query starts with special prefixes
  const isAskQuery = query.startsWith('ask:') || query.startsWith('?');
  const askText = isAskQuery
    ? query.replace(/^(ask:|^\?)/, '').trim()
    : '';

  // Filter nodes based on query
  const filteredNodes = query && !isAskQuery
    ? nodes
        .filter(n =>
          n.name.toLowerCase().includes(query.toLowerCase()) ||
          (n.path && n.path.toLowerCase().includes(query.toLowerCase()))
        )
        .slice(0, 8)
        .map(n => ({
          id: `node-${n.id}`,
          label: n.name,
          description: n.path,
          icon: getNodeIcon(n.type),
          action: () => { onNavigateToNode(n.id); onClose(); },
          category: 'node' as const,
        }))
    : [];

  // Filter commands based on query
  const filteredCommands = query && !isAskQuery
    ? commands.filter(c =>
        c.label.toLowerCase().includes(query.toLowerCase()) ||
        (c.description && c.description.toLowerCase().includes(query.toLowerCase()))
      )
    : commands.slice(0, 3); // Show first 3 commands when no query

  // All items
  const allItems: CommandItem[] = isAskQuery
    ? []
    : [...filteredCommands, ...filteredNodes];

  // Reset selection when items change
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(i => Math.min(i + 1, allItems.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (isAskQuery && askText) {
        onAskAI(askText);
        onOpenChat();
        onClose();
      } else if (allItems[selectedIndex]) {
        allItems[selectedIndex].action();
      }
    }
  }, [allItems, selectedIndex, isAskQuery, askText, onAskAI, onOpenChat, onClose]);

  // Scroll selected item into view
  useEffect(() => {
    const item = listRef.current?.querySelector(`[data-index="${selectedIndex}"]`);
    if (item) {
      item.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-background/80 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Palette */}
      <div
        className="relative w-full max-w-lg rounded-lg border bg-card shadow-xl overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        {/* Search input */}
        <div className="flex items-center border-b px-3 gap-2">
          <Command className="h-4 w-4 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            autoFocus
            placeholder="Type a command, search nodes, or ask:your question..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground"
            aria-label="Search commands and nodes"
          />
          <kbd className="hidden sm:inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
            esc
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-[300px] overflow-y-auto p-2" role="listbox">
          {/* Ask AI hint */}
          {isAskQuery && (
            <div className="px-2 py-3">
              <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                <MessageSquare className="h-4 w-4 text-primary" />
                <span>Ask AI:</span>
              </div>
              {askText ? (
                <div className="flex items-center justify-between p-2 rounded bg-muted/50">
                  <span className="text-sm">{askText}</span>
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <CornerDownLeft className="h-3 w-3" />
                    <span>to send</span>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Type your question after "ask:" or "?"
                </p>
              )}
            </div>
          )}

          {/* Commands */}
          {!isAskQuery && filteredCommands.length > 0 && (
            <div className="mb-2">
              <p className="px-2 py-1 text-xs font-medium text-muted-foreground">
                Commands
              </p>
              {filteredCommands.map((cmd, index) => (
                <button
                  key={cmd.id}
                  data-index={index}
                  onClick={cmd.action}
                  onMouseEnter={() => setSelectedIndex(index)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm text-left transition-colors",
                    selectedIndex === index ? "bg-accent" : "hover:bg-accent/50"
                  )}
                  role="option"
                  aria-selected={selectedIndex === index}
                >
                  <span className="text-muted-foreground">{cmd.icon}</span>
                  <span className="flex-1">{cmd.label}</span>
                  {cmd.shortcut && (
                    <kbd className="hidden sm:inline-flex text-[10px] text-muted-foreground">
                      {cmd.shortcut}
                    </kbd>
                  )}
                </button>
              ))}
            </div>
          )}

          {/* Nodes */}
          {!isAskQuery && filteredNodes.length > 0 && (
            <div>
              <p className="px-2 py-1 text-xs font-medium text-muted-foreground">
                Nodes
              </p>
              {filteredNodes.map((node, idx) => {
                const index = filteredCommands.length + idx;
                return (
                  <button
                    key={node.id}
                    data-index={index}
                    onClick={node.action}
                    onMouseEnter={() => setSelectedIndex(index)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm text-left transition-colors",
                      selectedIndex === index ? "bg-accent" : "hover:bg-accent/50"
                    )}
                    role="option"
                    aria-selected={selectedIndex === index}
                  >
                    {node.icon}
                    <span className="flex-1 truncate">{node.label}</span>
                    {node.description && (
                      <span className="text-xs text-muted-foreground truncate max-w-[150px]">
                        {node.description}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {/* Empty state */}
          {!isAskQuery && query && allItems.length === 0 && (
            <div className="px-2 py-6 text-center text-sm text-muted-foreground">
              <p>No results found for "{query}"</p>
              <p className="text-xs mt-1">Try "ask:{query}" to ask AI</p>
            </div>
          )}

          {/* Help hint when empty */}
          {!query && (
            <div className="px-2 py-3 text-xs text-muted-foreground space-y-1">
              <p><kbd className="px-1 rounded bg-muted">↑↓</kbd> to navigate</p>
              <p><kbd className="px-1 rounded bg-muted">enter</kbd> to select</p>
              <p><kbd className="px-1 rounded bg-muted">ask:</kbd> or <kbd className="px-1 rounded bg-muted">?</kbd> to ask AI</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
