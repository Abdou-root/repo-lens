import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { LoadingSpinner } from '@/components/ui/loading-spinner';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireAuth?: boolean;
}

/**
 * Protected Route component that guards routes requiring authentication
 *
 * Features:
 * - Redirects unauthenticated users to landing page
 * - Allows demo mode users
 * - Shows loading spinner while checking auth status
 * - Preserves intended destination for post-login redirect
 *
 * @param children - The component to render if authenticated
 * @param requireAuth - Whether authentication is required (default: true)
 */
export function ProtectedRoute({
  children,
  requireAuth = true,
}: ProtectedRouteProps) {
  const { user, isLoading, isDemoMode } = useAuth();
  const location = useLocation();

  // Show loading spinner while checking authentication status
  if (isLoading) {
    return <LoadingSpinner fullScreen />;
  }

  // Check if user is authenticated (either real user or demo mode)
  const isAuthenticated = user !== null || isDemoMode;

  // Redirect to landing page if authentication is required but user is not authenticated
  if (requireAuth && !isAuthenticated) {
    // Save the location they were trying to access for post-login redirect
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  // User is authenticated or auth not required, render the protected content
  return <>{children}</>;
}
