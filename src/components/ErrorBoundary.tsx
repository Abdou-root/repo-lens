import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home, Bug } from 'lucide-react';
import { Button } from '@/components/ui/button';
import * as Sentry from '@sentry/react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    if (!import.meta.env.PROD) {
      console.error('ErrorBoundary caught an error:', error, errorInfo);
    }

    this.setState({
      error,
      errorInfo,
    });

    // Report to Sentry in production
    if (import.meta.env.PROD) {
      Sentry.captureException(error, {
        contexts: {
          react: {
            componentStack: errorInfo.componentStack
          }
        }
      });
    }
  }

  private handleReset = () => {
    // Try to recover local state from localStorage
    try {
      const savedState = localStorage.getItem('repolens_graph_state');
      if (savedState) {
        localStorage.removeItem('repolens_graph_state');
      }
    } catch (e) {
      if (!import.meta.env.PROD) {
        console.error('Failed to clear saved state:', e);
      }
    }

    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  private handleGoHome = () => {
    window.location.href = '/';
  };

  private handleReportBug = () => {
    const GITHUB_REPO = import.meta.env.VITE_GITHUB_REPO || 'your-org/repolens';

    const errorDetails = `
Error: ${this.state.error?.message}
Stack: ${this.state.error?.stack}
Component Stack: ${this.state.errorInfo?.componentStack}
User Agent: ${navigator.userAgent}
URL: ${window.location.href}
    `.trim();

    const issueUrl = `https://github.com/${GITHUB_REPO}/issues/new?title=${encodeURIComponent(
      `Error: ${this.state.error?.message || 'Unknown error'}`
    )}&body=${encodeURIComponent(errorDetails)}`;

    window.open(issueUrl, '_blank');
  };

  public render() {
    if (this.state.hasError) {
      // Custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI
      return (
        <div className="min-h-screen flex items-center justify-center bg-background p-4">
          <div className="max-w-2xl w-full">
            <div className="bg-card border-2 border-destructive/20 rounded-2xl p-8 shadow-xl">
              {/* Error Icon */}
              <div className="flex justify-center mb-6">
                <div className="p-4 bg-destructive/10 rounded-full">
                  <AlertTriangle className="h-12 w-12 text-destructive" />
                </div>
              </div>

              {/* Error Title */}
              <h1 className="text-2xl font-bold text-center mb-3 text-foreground">
                Oops! Something went wrong
              </h1>

              {/* Error Message */}
              <p className="text-center text-muted-foreground mb-6">
                We encountered an unexpected error. Don't worry, your data is safe.
              </p>

              {/* Error Details (Collapsible) */}
              {this.state.error && (
                <details className="mb-6 bg-muted/50 rounded-lg p-4">
                  <summary className="cursor-pointer font-medium text-sm mb-2 hover:text-primary">
                    Technical Details
                  </summary>
                  <div className="space-y-2">
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground mb-1">
                        Error Code: ERR-001
                      </p>
                      <p className="text-sm font-mono text-destructive">
                        {this.state.error.message}
                      </p>
                    </div>
                    {this.state.error.stack && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground mb-1">
                          Stack Trace:
                        </p>
                        <pre className="text-xs font-mono bg-background p-2 rounded overflow-auto max-h-40">
                          {this.state.error.stack}
                        </pre>
                      </div>
                    )}
                  </div>
                </details>
              )}

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                <Button
                  onClick={this.handleReset}
                  variant="default"
                  size="lg"
                  className="gap-2"
                >
                  <RefreshCw className="h-4 w-4" />
                  Reload Page
                </Button>

                <Button
                  onClick={this.handleGoHome}
                  variant="outline"
                  size="lg"
                  className="gap-2"
                >
                  <Home className="h-4 w-4" />
                  Go to Dashboard
                </Button>

                <Button
                  onClick={this.handleReportBug}
                  variant="ghost"
                  size="lg"
                  className="gap-2"
                >
                  <Bug className="h-4 w-4" />
                  Report Bug
                </Button>
              </div>

              {/* Help Text */}
              <p className="text-center text-xs text-muted-foreground mt-6">
                If this problem persists, please{' '}
                <button
                  onClick={this.handleReportBug}
                  className="text-primary hover:underline"
                >
                  report it to our team
                </button>
                .
              </p>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
