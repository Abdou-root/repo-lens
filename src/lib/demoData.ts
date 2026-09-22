/**
 * Static demo data.
 *
 * Demo repositories are pre-parsed at build time by
 * `scripts/build_demo_data.py` into JSON files under `public/demo/`, so demo
 * mode works with the frontend hosted on its own, without the backend.
 */

import type { GraphEdge, GraphNode, Repository } from '@/types';

export interface DemoRepositoryInfo extends Repository {
  description?: string;
  language?: string;
  stars?: number;
}

export interface DemoGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const DEMO_BASE = `${import.meta.env.BASE_URL}demo`;

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${DEMO_BASE}/${path}`);
  if (!response.ok) {
    throw new Error(`Demo data not found: ${path} (${response.status})`);
  }
  return response.json() as Promise<T>;
}

/** Demo repositories are served as static files, so ids must not contain paths. */
function safeId(repoId: string): string {
  if (!/^[\w-]+$/.test(repoId)) {
    throw new Error(`Invalid demo repository id: ${repoId}`);
  }
  return repoId;
}

export function fetchDemoRepositories(): Promise<DemoRepositoryInfo[]> {
  return fetchJson<DemoRepositoryInfo[]>('repositories.json');
}

export function fetchDemoGraph(repoId: string): Promise<DemoGraph> {
  return fetchJson<DemoGraph>(`graph/${safeId(repoId)}.json`);
}

export function fetchDemoInsights<T = unknown>(repoId: string): Promise<T> {
  return fetchJson<T>(`insights/${safeId(repoId)}.json`);
}
