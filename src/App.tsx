import { lazy, Suspense } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { LoadingSpinner } from "@/components/ui/loading-spinner";

// Eager load landing page and auth callback for fast initial render
import LandingPage from "./pages/LandingPage";
import NotFound from "./pages/NotFound";
import { AuthCallback } from "./pages/AuthCallback";

// Lazy load heavy pages to improve initial bundle size
const Dashboard = lazy(() => import("./pages/Dashboard"));
const DemoPage = lazy(() => import("./pages/DemoPage"));
const GraphExplorer = lazy(() => import("./pages/GraphExplorer"));
const Settings = lazy(() => import("./pages/Settings"));

// Suspense fallback for lazy-loaded pages
const PageLoader = () => (
  <div className="flex items-center justify-center min-h-screen">
    <LoadingSpinner size="lg" />
  </div>
);

const App = () => (
  <TooltipProvider>
    <Toaster />
    <Sonner />
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/demo" element={<DemoPage />} />
          <Route path="/auth/callback" element={<AuthCallback />} />

          {/* Protected routes - require authentication or demo mode */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/graph/:repoId"
            element={
              <ProtectedRoute>
                <GraphExplorer />
              </ProtectedRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <Settings />
              </ProtectedRoute>
            }
          />

          {/* 404 page */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  </TooltipProvider>
);

export default App;
