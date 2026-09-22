import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { X, Send, Loader2, Trash2, Eye, FileCode, Box, Code } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { useStreamingChat } from '@/hooks/useStreamingChat';
import { MarkdownMessage } from './MarkdownMessage';
import { ThinkingIndicator } from '@/components/ui/thinking-indicator';
import { cn } from '@/lib/utils';
import { GraphNode } from '@/types';

interface ChatPanelProps {
  onClose: () => void;
  nodeContext?: string;  // Node name for display
  nodeId?: string;       // Full node ID for detailed context
  repoId?: string;
  repoName?: string;
  onNodeClick?: (nodeId: string) => void;  // Callback when clicking node links in AI responses
  selectedNode?: GraphNode | null;  // Full node details for context display
  totalNodes?: number;
  totalEdges?: number;
  autoSendQuestion?: boolean;  // Auto-send first suggested question
  onQuestionSent?: () => void;  // Callback after auto-sending
}

export function ChatPanel({ onClose, nodeContext, nodeId, repoId, repoName, onNodeClick, selectedNode, totalNodes, totalEdges, autoSendQuestion, onQuestionSent }: ChatPanelProps) {
  const [input, setInput] = useState('');
  const { messages, isStreaming, sendMessage, clearMessages } = useStreamingChat(repoId, repoName);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = useCallback(() => {
    if (!input.trim() || isStreaming) return;
    sendMessage(input, nodeContext, nodeId);
    setInput('');
  }, [input, isStreaming, sendMessage, nodeContext, nodeId]);

  // Generate contextual suggestions based on selected node
  const suggestedQuestions = useMemo(() => {
    if (selectedNode) {
      switch (selectedNode.type) {
        case 'function':
          return [
            `What does ${selectedNode.name} do?`,
            `What functions call ${selectedNode.name}?`,
            `Are there any edge cases in ${selectedNode.name}?`,
          ];
        case 'class':
          return [
            `Explain the purpose of ${selectedNode.name}`,
            `What are the key methods in ${selectedNode.name}?`,
            `What design pattern does ${selectedNode.name} follow?`,
          ];
        case 'file':
          return [
            `Summarize what's in ${selectedNode.name}`,
            `What are the main exports from ${selectedNode.name}?`,
            `How does ${selectedNode.name} fit into the architecture?`,
          ];
        case 'folder':
          return [
            `What's the purpose of the ${selectedNode.name} module?`,
            `How do components in ${selectedNode.name} interact?`,
            `What's the responsibility of ${selectedNode.name}?`,
          ];
        default:
          return [
            'Explain the overall architecture',
            'What design patterns are used?',
            'How does data flow through the system?',
          ];
      }
    }
    return [
      'Explain the overall architecture',
      'What design patterns are used?',
      'How does data flow through the system?',
    ];
  }, [selectedNode]);

  // Auto-send first suggested question when button is clicked
  useEffect(() => {
    if (autoSendQuestion && suggestedQuestions.length > 0 && messages.length === 0) {
      // Send the first suggested question automatically
      const firstQuestion = suggestedQuestions[0];
      sendMessage(firstQuestion, nodeContext, nodeId);
      onQuestionSent?.();
    }
  }, [autoSendQuestion, suggestedQuestions, messages.length, nodeContext, nodeId, sendMessage, onQuestionSent]);

  // Get icon for node type
  const getNodeIcon = () => {
    if (!selectedNode) return Eye;
    switch (selectedNode.type) {
      case 'function': return Code;
      case 'class': return Box;
      case 'file': return FileCode;
      case 'folder': return FileCode;
      default: return Eye;
    }
  };

  const NodeIcon = getNodeIcon();

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border">
        <div className="flex-1">
          <h3 className="font-semibold">AI Assistant</h3>
          {selectedNode ? (
            <div className="mt-2 space-y-1.5">
              <div className="flex items-center gap-2">
                <NodeIcon className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium truncate max-w-[250px]">
                  {selectedNode.name}
                </span>
                <Badge variant="secondary" className="text-xs capitalize">
                  {selectedNode.type}
                </Badge>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Eye className="h-3 w-3" />
                <span>Analyzing this file only (not full repository)</span>
              </div>
            </div>
          ) : (
            <div className="mt-2 space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Full repository context</p>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground/70">
                <Eye className="h-3 w-3" />
                <span>{totalNodes || 0} nodes, {totalEdges || 0} edges</span>
              </div>
            </div>
          )}
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="icon"
              onClick={clearMessages}
              title="Clear chat history"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Ask questions about the codebase. I can explain architecture, dependencies, and code patterns.
            </p>
            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Suggested questions:</p>
              {suggestedQuestions.map((q, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(q, nodeContext, nodeId)}
                  className="block w-full text-left text-sm p-3 rounded-xl border border-border bg-gradient-to-r from-muted/30 to-transparent hover:bg-muted/50 hover:border-primary/20 hover:shadow-sm transition-all duration-200 animate-fade-in-up"
                  style={{ animationDelay: `${i * 100}ms` }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg, index) => {
              // Skip rendering empty AI messages (ThinkingIndicator will show instead)
              if (msg.role === 'assistant' && !msg.content) {
                return null;
              }
              return (
                <div
                  key={msg.id}
                  className={cn(
                    'rounded-2xl p-3 animate-fade-in-up shadow-sm relative overflow-hidden',
                    msg.role === 'user'
                      ? 'bg-gradient-to-br from-primary to-primary/90 text-primary-foreground ml-8 text-sm shadow-md'
                      : 'bg-gradient-to-br from-muted to-muted/80 border border-border/50 mr-8 group',
                    // Add glow effect to new AI messages that are still streaming
                    msg.role === 'assistant' && isStreaming && index === messages.length - 1 && 'animate-pulse-glow'
                  )}
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  {/* Shimmer overlay for streaming AI messages */}
                  {msg.role === 'assistant' && isStreaming && index === messages.length - 1 && (
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-primary/5 to-transparent animate-shimmer pointer-events-none" />
                  )}
                  {msg.role === 'user' ? (
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  ) : (
                    <div className="relative z-10">
                      <MarkdownMessage content={msg.content} onNodeClick={onNodeClick} />
                      {isStreaming && msg.content && (
                        <span className="inline-block w-1 h-4 bg-primary animate-pulse ml-0.5 rounded-sm" />
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {isStreaming && messages[messages.length - 1]?.content === '' && (
              <ThinkingIndicator />
            )}
          </div>
        )}
      </ScrollArea>

      {/* Input */}
      <div className="p-4 border-t border-border">
        <div className="flex gap-2">
          <Textarea
            placeholder="Ask about the code..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            className="min-h-[80px] resize-none"
          />
        </div>
        <div className="flex justify-end mt-2">
          <Button onClick={handleSend} disabled={!input.trim() || isStreaming}>
            {isStreaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            <span className="ml-2">Send</span>
          </Button>
        </div>
      </div>
    </div>
  );
}
