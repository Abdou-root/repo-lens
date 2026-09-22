// Graph Node and Edge Types
export interface GraphNode {
  id: string;
  type: 'file' | 'class' | 'function' | 'folder';
  name: string;
  path: string;
  summary?: string;
  code?: string;
  lineCount?: number;
  // For folder nodes
  childCount?: number;
  isCollapsed?: boolean;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: 'imports' | 'calls' | 'inherits' | 'external' | 'defines';
}

// Repository Types
export interface Repository {
  id: string;
  name: string;
  url: string;
  status: 'queued' | 'parsing' | 'complete' | 'error';
  nodeCount: number;
  edgeCount: number;
  fileCount: number;
  lastAnalyzed?: string;
  isDemo?: boolean;
  progress?: {
    current: number;
    total: number;
  };
}

export interface ParseStatus {
  repoId: string;
  status: 'queued' | 'parsing' | 'complete' | 'error';
  progress: { current: number; total: number };
  message?: string;
}

// Chat Types
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  nodeContext?: string;
}

// User Types
export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  githubUsername?: string;
}
