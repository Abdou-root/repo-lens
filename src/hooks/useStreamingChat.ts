import { useState, useCallback, useEffect, useRef } from 'react';
import { ChatMessage } from '@/types';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

// Helper to get storage key for a repo
const getStorageKey = (repoId?: string) => repoId ? `repolens_chat_${repoId}` : null;

// Helper to serialize messages for storage (convert Date to string)
const serializeMessages = (messages: ChatMessage[]): string => {
  return JSON.stringify(messages.map(msg => ({
    ...msg,
    timestamp: msg.timestamp.toISOString(),
  })));
};

// Helper to deserialize messages from storage (convert string back to Date)
const deserializeMessages = (stored: string): ChatMessage[] => {
  try {
    const parsed = JSON.parse(stored);
    return parsed.map((msg: ChatMessage & { timestamp: string }) => ({
      ...msg,
      timestamp: new Date(msg.timestamp),
    }));
  } catch {
    return [];
  }
};

export function useStreamingChat(repoId?: string, repoName?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const { isDemoMode } = useAuth();
  const abortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);

  // Load messages from localStorage on mount or when repoId changes
  useEffect(() => {
    const storageKey = getStorageKey(repoId);
    if (storageKey) {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const restored = deserializeMessages(saved);
        if (restored.length > 0) {
          setMessages(restored);
        }
      }
    }
  }, [repoId]);

  // Track mounted state and cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      // Abort any pending streams
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Save messages to localStorage whenever they change
  useEffect(() => {
    const storageKey = getStorageKey(repoId);
    if (storageKey && messages.length > 0) {
      localStorage.setItem(storageKey, serializeMessages(messages));
    }
  }, [messages, repoId]);

  const sendMessage = useCallback(async (content: string, nodeContext?: string, nodeId?: string) => {
    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
      nodeContext,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsStreaming(true);

    // Create assistant message placeholder
    const assistantMessage: ChatMessage = {
      id: `msg-${Date.now() + 1}`,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, assistantMessage]);

    // In demo mode, use mock response
    if (isDemoMode) {
      const mockResponse = `I'm analyzing the codebase structure. This repository follows a modular architecture pattern with clear separation of concerns.

Key observations:
- **Middleware Pattern**: Requests flow through a chain of middleware functions
- **Factory Pattern**: The main export is a factory function that creates instances
- **Event-Driven**: Uses event emitters for async operations

Would you like me to explain any specific component in more detail?`;

      // Simulate streaming
      for (let i = 0; i <= mockResponse.length; i++) {
        if (!isMountedRef.current) return; // Stop if unmounted
        await new Promise((resolve) => setTimeout(resolve, 15));
        if (!isMountedRef.current) return; // Check again after await
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessage.id
              ? { ...msg, content: mockResponse.slice(0, i) }
              : msg
          )
        );
      }
      if (isMountedRef.current) {
        setIsStreaming(false);
      }
      return;
    }

    // Use real API streaming with abort controller
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      await api.streamSSE(
        '/api/chat/stream',
        {
          repo_id: repoId,
          repo_name: repoName,
          node_context: nodeContext,
          node_id: nodeId,  // Full node ID for detailed context
          messages: [...messages, userMessage].map(msg => ({
            role: msg.role,
            content: msg.content,
            timestamp: msg.timestamp.toISOString(),
          })),
        },
        (data) => {
          if (!isMountedRef.current) return; // Guard against unmounted updates

          if (data.type === 'delta') {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessage.id
                  ? { ...msg, content: msg.content + data.message.content }
                  : msg
              )
            );
          } else if (data.type === 'done') {
            setIsStreaming(false);
          }
        },
        (error) => {
          if (!isMountedRef.current) return; // Guard against unmounted updates

          if (!import.meta.env.PROD) {
            console.error('Chat streaming error:', error);
          }
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessage.id
                ? { ...msg, content: 'Error: Failed to get response from AI' }
                : msg
            )
          );
          setIsStreaming(false);
        },
        () => {
          if (!isMountedRef.current) return; // Guard against unmounted updates
          setIsStreaming(false);
        },
        abortController.signal // Pass abort signal
      );
    } catch (error) {
      // Ignore abort errors
      if (error instanceof Error && error.name === 'AbortError') {
        return;
      }

      if (!isMountedRef.current) return; // Guard against unmounted updates

      if (!import.meta.env.PROD) {
        console.error('Failed to send message:', error);
      }
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessage.id
            ? { ...msg, content: 'Error: Failed to connect to chat service' }
            : msg
        )
      );
      setIsStreaming(false);
    } finally {
      // Clear abort controller ref if this was the active one
      if (abortControllerRef.current === abortController) {
        abortControllerRef.current = null;
      }
    }
  }, [messages, isDemoMode, repoId, repoName]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    // Also clear from localStorage
    const storageKey = getStorageKey(repoId);
    if (storageKey) {
      localStorage.removeItem(storageKey);
    }
  }, [repoId]);

  return { messages, isStreaming, sendMessage, clearMessages };
}
