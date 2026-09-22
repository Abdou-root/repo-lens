import { useState, useEffect, useRef, useCallback } from 'react';
import { Plus, GitBranch, Loader2, CheckCircle2, AlertCircle, Trash2, Download, FileCode, Database, Brain, Sparkles, Check, FolderGit2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Header } from '@/components/layout/Header';
import { EmptyState } from '@/components/ui/EmptyState';
import { useNavigate } from 'react-router-dom';
import { Repository } from '@/types';
import { Progress } from '@/components/ui/progress';
import { api } from '@/lib/api';
import { fetchDemoRepositories } from '@/lib/demoData';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { useOnboarding } from '@/contexts/OnboardingContext';
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard';
import { trackEvent, Events } from '@/lib/analytics';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

// Step definitions with labels and icons
const STEP_CONFIG = {
  initializing: { label: 'Initializing...', icon: Loader2, order: 0 },
  cloning: { label: 'Cloning repository...', icon: Download, order: 1 },
  parsing: { label: 'Parsing files...', icon: FileCode, order: 2 },
  persisting: { label: 'Saving to database...', icon: Database, order: 3 },
  embedding: { label: 'Generating embeddings...', icon: Brain, order: 4 },
  summarizing: { label: 'AI summarization...', icon: Sparkles, order: 5 },
  finalizing: { label: 'Finalizing...', icon: Check, order: 6 },
} as const;

type StepKey = keyof typeof STEP_CONFIG;

// Helper function to format seconds to human-readable time
function formatETA(seconds: number): string {
  if (seconds < 60) {
    return `~${Math.round(seconds)}s`;
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.round(seconds % 60);
    return `~${minutes}m ${remainingSeconds}s`;
  } else {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `~${hours}h ${minutes}m`;
  }
}

interface ProgressData {
  current: number;
  total: number;
  step?: StepKey;
  message?: string;
  metadata?: {
    elapsed_seconds?: number;
    eta_seconds?: number;
    processing_rate?: number;
    nodes_count?: number;
    edges_count?: number;
    files_count?: number;
    functions_indexed?: number;
    classes_indexed?: number;
  };
}

export default function Dashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, isDemoMode } = useAuth();
  const { hasCompletedOnboarding } = useOnboarding();
  const [repoUrl, setRepoUrl] = useState('');
  const [repoProgress, setRepoProgress] = useState<Record<string, ProgressData>>({});
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [repoToDelete, setRepoToDelete] = useState<Repository | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Fetch user repositories from backend (use user instead of token for httpOnly cookie auth)
  const { data: userRepos = [], isLoading } = useQuery({
    queryKey: ['repos'],
    queryFn: () => api.get<Repository[]>('/api/repos'),
    enabled: !!user && !isDemoMode,
  });

  // Demo repositories are pre-parsed static files, so they work without a backend
  const { data: demoRepos = [], isLoading: isDemoLoading } = useQuery({
    queryKey: ['demo-repos'],
    queryFn: fetchDemoRepositories,
    enabled: isDemoMode,
  });

  // Create repository mutation
  const addRepoMutation = useMutation({
    mutationFn: async (url: string) => {
      return api.post<Repository>('/api/repos', { url });
    },
    onSuccess: (repo) => {
      // Track repo creation
      trackEvent(Events.REPO_CREATED, {
        repo_id: repo.id,
        repo_name: repo.name,
      });
      
      // Invalidate and refetch repos
      queryClient.invalidateQueries({ queryKey: ['repos'] });
      // Subscribe to progress updates
      subscribeToProgress(repo.id);
    },
  });

  // Delete repository mutation
  const deleteRepoMutation = useMutation({
    mutationFn: async (repoId: string) => {
      return api.delete(`/api/repos/${repoId}`);
    },
    onSuccess: (_, repoId) => {
      // Invalidate and refetch repos
      queryClient.invalidateQueries({ queryKey: ['repos'] });
      // Clear chat history from localStorage
      localStorage.removeItem(`repolens_chat_${repoId}`);
      // Close dialog
      setDeleteDialogOpen(false);
      setRepoToDelete(null);
    },
  });

  const handleAddRepo = () => {
    const trimmedUrl = repoUrl.trim();

    // Validate not empty
    if (!trimmedUrl) {
      return;
    }

    // Validate GitHub URL format
    const GITHUB_URL_REGEX = /^https?:\/\/(www\.)?github\.com\/[\w-]+\/[\w.-]+\/?$/;
    if (!GITHUB_URL_REGEX.test(trimmedUrl)) {
      // Note: Toast is imported via the useMutation hooks which handle success/error toasts
      // For now, we'll rely on the API error handling
      return;
    }

    // Check for duplicates
    const isDuplicate = allRepos.some(repo =>
      repo.url?.toLowerCase() === trimmedUrl.toLowerCase()
    );

    if (isDuplicate) {
      // The mutation will handle showing the error
      return;
    }

    // Prevent multiple submissions
    if (addRepoMutation.isPending) return;

    addRepoMutation.mutate(trimmedUrl);
    setRepoUrl('');
  };

  const handleDeleteClick = (e: React.MouseEvent, repo: Repository) => {
    e.stopPropagation(); // Prevent navigating to the repo
    setRepoToDelete(repo);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = () => {
    if (repoToDelete) {
      deleteRepoMutation.mutate(repoToDelete.id);
    }
  };

  // Ref to track active EventSource connections
  const eventSourcesRef = useRef<Map<string, EventSource>>(new Map());

  // Subscribe to SSE progress updates
  const subscribeToProgress = useCallback((repoId: string) => {
    // Close existing connection if any
    const existing = eventSourcesRef.current.get(repoId);
    if (existing) {
      existing.close();
    }

    const eventSource = api.createEventSource(`/api/repos/${repoId}/events`);
    eventSourcesRef.current.set(repoId, eventSource);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.progress) {
        setRepoProgress(prev => ({
          ...prev,
          [repoId]: {
            current: data.progress.current,
            total: data.progress.total,
            step: data.step as StepKey,
            message: data.message,
            metadata: data.metadata,
          },
        }));
      }

      if (data.type === 'done') {
        // Refetch repositories to get updated stats
        queryClient.invalidateQueries({ queryKey: ['repos'] });
        // Clear progress
        setRepoProgress(prev => {
          const newProgress = { ...prev };
          delete newProgress[repoId];
          return newProgress;
        });
        eventSource.close();
        eventSourcesRef.current.delete(repoId);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      eventSourcesRef.current.delete(repoId);
    };
  }, [queryClient]);

  // Auto-subscribe to progress for repositories that are already parsing/queued
  useEffect(() => {
    if (!isDemoMode && userRepos.length > 0) {
      const activeRepos = userRepos.filter(
        repo => repo.status === 'parsing' || repo.status === 'queued'
      );

      activeRepos.forEach(repo => {
        // Only subscribe if we're not already tracking this repo's progress
        if (!repoProgress[repo.id]) {
          subscribeToProgress(repo.id);
        }
      });
    }
  }, [userRepos, isDemoMode, repoProgress, subscribeToProgress]);

  // Show onboarding for first-time users
  useEffect(() => {
    if (!hasCompletedOnboarding && userRepos.length === 0 && demoRepos.length > 0) {
      // Small delay to let the dashboard render first
      const timer = setTimeout(() => {
        setShowOnboarding(true);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [hasCompletedOnboarding, userRepos.length, demoRepos.length]);

  // Cleanup SSE connections on unmount
  useEffect(() => {
    return () => {
      // Close all EventSource connections on unmount
      eventSourcesRef.current.forEach((eventSource) => {
        eventSource.close();
      });
      eventSourcesRef.current.clear();
    };
  }, []);

  const allRepos = isDemoMode ? demoRepos : userRepos;
  const currentLoading = isDemoMode ? isDemoLoading : isLoading;

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container py-8">
        <div className="flex flex-col gap-8">
          {/* Header */}
          <div>
            <h1 className="text-3xl font-bold">Dashboard</h1>
            <p className="text-muted-foreground">Manage and explore your analyzed repositories</p>
          </div>

          {/* Add Repository */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Add Repository</CardTitle>
              <CardDescription>Paste a GitHub URL to start analysis immediately</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-3">
                <Input
                  placeholder="https://github.com/owner/repo"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !addRepoMutation.isPending && handleAddRepo()}
                  disabled={isDemoMode}
                />
                <Button
                  onClick={handleAddRepo}
                  disabled={addRepoMutation.isPending || !repoUrl.trim() || isDemoMode}
                >
                  {addRepoMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  <span className="ml-2">Analyze</span>
                </Button>
              </div>

              {isDemoMode && (
                <p className="text-xs text-muted-foreground mt-2">
                  Repository creation is disabled in demo mode
                </p>
              )}

              {/* Parsing Progress */}
              {!isDemoMode && userRepos.filter(repo => repo.status === 'parsing' || repo.status === 'queued').map(repo => {
                const progress = repoProgress[repo.id];
                const progressPercent = progress?.current ?? 0;
                const currentStep = progress?.step;
                const stepConfig = currentStep ? STEP_CONFIG[currentStep] : null;
                const StepIcon = stepConfig?.icon ?? Loader2;

                return (
                  <div key={repo.id} className="mt-4 p-4 rounded-lg bg-muted/30 border border-border">
                    {/* Header with repo name and time info */}
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-medium">{repo.name}</span>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        {progress?.metadata?.eta_seconds !== undefined && progress.metadata.eta_seconds > 0 && (
                          <span className="font-medium text-primary">
                            {formatETA(progress.metadata.eta_seconds)} remaining
                          </span>
                        )}
                        {progress?.metadata?.elapsed_seconds && (
                          <span>
                            {Math.round(progress.metadata.elapsed_seconds)}s elapsed
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Step indicator with icon */}
                    <div className="flex items-center gap-3 mb-3">
                      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary/10">
                        <StepIcon className="h-4 w-4 text-primary animate-pulse" />
                      </div>
                      <div className="flex-1">
                        <div className="flex justify-between items-center mb-1">
                          <span className="text-sm font-medium">
                            {stepConfig?.label ?? (repo.status === 'queued' ? 'Waiting to start...' : 'Processing...')}
                          </span>
                          <span className="text-sm font-mono text-muted-foreground">
                            {progressPercent}%
                          </span>
                        </div>
                        <Progress value={progressPercent} className="h-2" />
                      </div>
                    </div>

                    {/* Step timeline */}
                    <div className="flex items-center gap-1 mt-3">
                      {Object.entries(STEP_CONFIG).map(([key, config]) => {
                        const stepOrder = config.order;
                        const currentOrder = stepConfig?.order ?? -1;
                        const isCompleted = stepOrder < currentOrder;
                        const isCurrent = stepOrder === currentOrder;

                        return (
                          <div
                            key={key}
                            className={`flex-1 h-1 rounded-full transition-colors ${
                              isCompleted
                                ? 'bg-primary'
                                : isCurrent
                                ? 'bg-primary/50'
                                : 'bg-muted'
                            }`}
                            title={config.label}
                          />
                        );
                      })}
                    </div>

                    {/* Metadata stats */}
                    {progress?.metadata && (
                      <div className="flex flex-wrap gap-4 mt-3 text-xs text-muted-foreground">
                        {progress.metadata.files_count !== undefined && progress.metadata.files_count > 0 && (
                          <span>{progress.metadata.files_count} files</span>
                        )}
                        {progress.metadata.nodes_count !== undefined && progress.metadata.nodes_count > 0 && (
                          <span>{progress.metadata.nodes_count} nodes</span>
                        )}
                        {progress.metadata.functions_indexed !== undefined && progress.metadata.functions_indexed > 0 && (
                          <span>{progress.metadata.functions_indexed} functions indexed</span>
                        )}
                        {progress.metadata.processing_rate !== undefined && progress.metadata.processing_rate > 0 && (
                          <span className="text-primary">{progress.metadata.processing_rate.toFixed(1)} nodes/s</span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* Repository Grid */}
          <div>
            <h2 className="text-xl font-semibold mb-4">
              {isDemoMode ? 'Demo Repositories' : 'Your Repositories'}
            </h2>
            {currentLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : allRepos.length === 0 ? (
              <EmptyState
                icon={FolderGit2}
                title="No repositories yet"
                description={isDemoMode ? "Demo repositories are being loaded. Please wait..." : "Get started by adding a GitHub repository above. We'll analyze it and build an interactive knowledge graph for you."}
                action={!isDemoMode ? {
                  label: "Add Repository",
                  onClick: () => document.querySelector<HTMLInputElement>('input[placeholder*="github"]')?.focus()
                } : undefined}
              />
            ) : (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                {allRepos.map((repo) => (
                  <RepoCard
                    key={repo.id}
                    repo={repo}
                    onClick={() => {
                      trackEvent(Events.REPO_VIEWED, { repo_id: repo.id });
                      navigate(`/graph/${repo.id}`);
                    }}
                    onDelete={!isDemoMode ? (e) => handleDeleteClick(e, repo) : undefined}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Repository</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <strong>{repoToDelete?.name}</strong>?
              This will permanently remove all analyzed data, including nodes, edges, and chat history.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteRepoMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Onboarding Wizard */}
      <OnboardingWizard
        open={showOnboarding}
        onClose={() => setShowOnboarding(false)}
      />
    </div>
  );
}

interface RepoCardProps {
  repo: Repository;
  onClick: () => void;
  onDelete?: (e: React.MouseEvent) => void;
}

function RepoCard({ repo, onClick, onDelete }: RepoCardProps) {
  const statusIcon = {
    complete: <CheckCircle2 className="h-4 w-4 text-success" />,
    parsing: <Loader2 className="h-4 w-4 animate-spin text-chart-1" />,
    queued: <GitBranch className="h-4 w-4 text-muted-foreground" />,
    error: <AlertCircle className="h-4 w-4 text-destructive" />,
  };

  return (
    <Card
      className="cursor-pointer group relative overflow-hidden"
      onClick={onClick}
    >
      {/* Hover gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

      <CardContent className="pt-6 relative">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-muted/50 group-hover:bg-primary/10 transition-colors">
              <GitBranch className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
            <span className="font-semibold">{repo.name}</span>
          </div>
          <div className="flex items-center gap-2">
            {statusIcon[repo.status]}
            {onDelete && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                onClick={onDelete}
                title="Delete repository"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        {repo.isDemo && (
          <span className="inline-block text-xs bg-primary/10 text-primary px-2 py-1 rounded-full font-medium mb-3">
            Demo
          </span>
        )}

        <div className="grid grid-cols-3 gap-2 text-center rounded-lg bg-muted/30 p-3">
          <div>
            <p className="text-lg font-bold text-primary">{repo.nodeCount}</p>
            <p className="text-xs text-muted-foreground">Nodes</p>
          </div>
          <div>
            <p className="text-lg font-bold text-primary">{repo.edgeCount}</p>
            <p className="text-xs text-muted-foreground">Edges</p>
          </div>
          <div>
            <p className="text-lg font-bold text-primary">{repo.fileCount}</p>
            <p className="text-xs text-muted-foreground">Files</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
