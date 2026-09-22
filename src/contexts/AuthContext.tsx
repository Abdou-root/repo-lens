import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../lib/api';
import { toast } from 'sonner';

interface User {
  github_id: number;
  email: string;
  name: string;
  avatar_url: string;
  username?: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: () => void;
  logout: () => void;
  isLoading: boolean;
  isDemoMode: boolean;
  enterDemoMode: () => void;
  exitDemoMode: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Token storage keys
const ACCESS_TOKEN_KEY = 'repolens_access_token';
const REFRESH_TOKEN_KEY = 'repolens_refresh_token';
const USER_KEY = 'repolens_user';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Initialize user from localStorage if available
  const [user, setUser] = useState<User | null>(() => {
    const storedUser = localStorage.getItem(USER_KEY);
    return storedUser ? JSON.parse(storedUser) : null;
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isDemoMode, setIsDemoMode] = useState(false);

  const fetchCurrentUser = useCallback(async () => {
    // Check if we have a token before making the request
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      // Backend will check Authorization header (set by api client)
      const data = await api.get<User>('/api/auth/me');
      setUser(data);
      localStorage.setItem(USER_KEY, JSON.stringify(data));

      // Auto-exit demo mode when user successfully authenticates
      const storedDemoMode = localStorage.getItem('demoMode');
      if (storedDemoMode === 'true') {
        localStorage.removeItem('demoMode');
        setIsDemoMode(false);
      }
    } catch (error) {
      // Token might be expired - clear it
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Check demo mode first
    const storedDemoMode = localStorage.getItem('demoMode');
    if (storedDemoMode === 'true') {
      setIsDemoMode(true);
      setIsLoading(false);
      return;
    }

    // Check if we have tokens in localStorage
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (token) {
      // Validate token by fetching current user
      fetchCurrentUser();
    } else {
      setIsLoading(false);
    }
  }, [fetchCurrentUser]);

  // Refetch user when navigating to dashboard (catches OAuth redirects)
  useEffect(() => {
    const checkAuthOnNavigation = () => {
      // If we're on dashboard and don't have a user yet, refetch
      if (window.location.pathname === '/dashboard' && !user && !isDemoMode) {
        fetchCurrentUser();
      }
    };

    // Check immediately on mount
    checkAuthOnNavigation();

    // Listen for navigation events (for OAuth redirects)
    const handlePopState = () => checkAuthOnNavigation();
    const handlePushState = () => checkAuthOnNavigation();

    window.addEventListener('popstate', handlePopState);

    // Intercept pushState and replaceState to detect navigation
    const originalPushState = window.history.pushState;
    const originalReplaceState = window.history.replaceState;

    window.history.pushState = function(...args) {
      originalPushState.apply(this, args);
      handlePushState();
    };

    window.history.replaceState = function(...args) {
      originalReplaceState.apply(this, args);
      handlePushState();
    };

    return () => {
      window.removeEventListener('popstate', handlePopState);
      window.history.pushState = originalPushState;
      window.history.replaceState = originalReplaceState;
    };
  }, [user, isDemoMode, fetchCurrentUser]);

  const login = () => {
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    window.location.href = `${apiUrl}/api/auth/github`;
  };

  const logout = async () => {
    if (!user && !isDemoMode) return;

    try {
      // Call backend to blacklist token
      await api.post('/api/auth/logout');
      toast.success('Logged out successfully');
    } catch (error) {
      // Even if backend call fails, clear local state
      if (!import.meta.env.PROD) {
        console.error('Logout failed:', error);
      }
    }

    // Clear localStorage tokens
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem('demoMode');
    setUser(null);
    setIsDemoMode(false);
  };

  const enterDemoMode = useCallback(() => {
    setIsDemoMode(true);
    localStorage.setItem('demoMode', 'true');
  }, []);

  const exitDemoMode = useCallback(() => {
    setIsDemoMode(false);
    localStorage.removeItem('demoMode');
  }, []);

  // Get current access token for components that need it
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);

  return (
    <AuthContext.Provider value={{
      user,
      token,
      login,
      logout,
      isLoading,
      isDemoMode,
      enterDemoMode,
      exitDemoMode
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
