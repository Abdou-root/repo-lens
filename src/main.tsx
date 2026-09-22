import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import { AuthProvider } from "./contexts/AuthContext";
import { OnboardingProvider } from "./contexts/OnboardingContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { initSentry } from "./lib/sentry";
import * as serviceWorkerRegistration from "./lib/serviceWorkerRegistration";

// Initialize Sentry for error tracking
initSentry();

// Initialize analytics
import { analytics } from './lib/analytics';

// Initialize Web Vitals tracking
import { initWebVitals } from './lib/webVitals';
initWebVitals();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <OnboardingProvider>
            <App />
          </OnboardingProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </ErrorBoundary>
);

// Register service worker for PWA support
serviceWorkerRegistration.register({
  onSuccess: () => {
    if (!import.meta.env.PROD) {
      console.log('RepoLens is now available offline!');
    }
  },
  onUpdate: (registration) => {
    if (!import.meta.env.PROD) {
      console.log('New version available! Please refresh.');
    }
    // Optionally show a toast notification to the user
    if (registration.waiting) {
      registration.waiting.postMessage({ type: 'SKIP_WAITING' });
      window.location.reload();
    }
  },
});
