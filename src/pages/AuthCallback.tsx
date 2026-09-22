import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export function AuthCallback() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Extract tokens from URL fragment
    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);

    const accessToken = params.get('access_token');
    const refreshToken = params.get('refresh_token');
    const userParam = params.get('user');

    // Clear URL fragment immediately (security - don't leave tokens in browser history)
    window.history.replaceState(null, '', window.location.pathname);

    if (!accessToken || !refreshToken) {
      setError('Authentication failed - missing tokens');
      setTimeout(() => navigate('/'), 3000);
      return;
    }

    try {
      const user = userParam ? JSON.parse(decodeURIComponent(userParam)) : null;

      // Store tokens in localStorage
      localStorage.setItem('repolens_access_token', accessToken);
      localStorage.setItem('repolens_refresh_token', refreshToken);
      if (user) {
        localStorage.setItem('repolens_user', JSON.stringify(user));
      }

      // Redirect to dashboard
      navigate('/dashboard', { replace: true });
    } catch (e) {
      console.error('Failed to process auth callback:', e);
      setError('Failed to process authentication');
      setTimeout(() => navigate('/'), 3000);
    }
  }, [navigate]);

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <div className="text-center">
          <p className="text-red-500">{error}</p>
          <p className="text-muted-foreground mt-2">Redirecting...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
        <p className="text-muted-foreground mt-4">Completing sign in...</p>
      </div>
    </div>
  );
}
