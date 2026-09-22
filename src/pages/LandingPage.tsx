import { Eye, Github, ArrowRight, Database, Brain, GitBranch } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { TechStackModal } from '@/components/landing/TechStackModal';
import { AnimatedGraphPreview } from '@/components/landing/AnimatedGraphPreview';
import { useState, useEffect } from 'react';
import { updateSEO } from '@/lib/seo';
import { toast } from 'sonner';

export default function LandingPage() {
  const { user, login, enterDemoMode } = useAuth();
  const navigate = useNavigate();
  const [techModalOpen, setTechModalOpen] = useState(false);

  const handleTryDemo = () => {
    enterDemoMode();
    navigate('/demo');
  };

  const handleLogin = () => {
    login();
  };
  
  // Update SEO for landing page
  useEffect(() => {
    updateSEO({
      title: 'RepoLens - Code Visualization',
      description: 'Transform your code repositories into interactive knowledge graphs with AI-powered insights',
    });
  }, []);

  // Handle OAuth error redirects
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const error = params.get('error');

    if (error) {
      if (error === 'invalid_state') {
        toast.error('Authentication failed. Please try again.');
      } else if (error === 'failed_to_get_user') {
        toast.error('Failed to retrieve GitHub user info. Please try again.');
      } else {
        toast.error('Authentication error. Please try again.');
      }
      // Clear error from URL
      window.history.replaceState({}, '', '/');
    }
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <Header />

      {/* Hero Section with gradient background */}
      <section className="relative overflow-hidden">
        {/* Decorative background blurs */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary/5 rounded-full blur-3xl" />
          <div className="absolute top-20 -left-20 w-64 h-64 bg-accent/30 rounded-full blur-3xl" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-96 h-64 bg-warning/5 rounded-full blur-3xl" />
        </div>

        <div className="container py-16 lg:py-24 relative">
          <div className="flex flex-col items-center text-center gap-6 max-w-4xl mx-auto">
            <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-muted/80 backdrop-blur-sm text-muted-foreground text-sm shadow-sm border border-border/50 animate-fade-in-up">
              <Eye className="h-4 w-4" />
              <span>Code Architecture Visualization</span>
            </div>

            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight animate-fade-in-up stagger-1">
              Visualize Any Codebase{' '}
              <span className="text-gradient-primary">in Seconds</span>
            </h1>

            <p className="text-lg md:text-xl text-muted-foreground max-w-2xl animate-fade-in-up stagger-2">
              Transform complex repositories into interactive knowledge graphs.
              Understand code relationships, explore dependencies, and get AI-powered explanations.
            </p>

            {user && (
              <p className="text-sm text-muted-foreground animate-fade-in-up stagger-2">
                Welcome back, {user.name}!
              </p>
            )}

            <div className="flex flex-col sm:flex-row gap-3 animate-fade-in-up stagger-3">
              <Button size="xl" onClick={handleTryDemo} className="gap-2 shadow-lg shadow-primary/25">
                Try Demo
                <ArrowRight className="h-4 w-4" />
              </Button>

              {user ? (
                <Button
                  size="xl"
                  variant="outline"
                  onClick={() => navigate('/dashboard')}
                  className="gap-2"
                >
                  <GitBranch className="h-4 w-4" />
                  Go to Dashboard
                </Button>
              ) : (
                <Button
                  size="xl"
                  variant="outline"
                  onClick={handleLogin}
                  className="gap-2"
                >
                  <Github className="h-4 w-4" />
                  Connect GitHub
                </Button>
              )}
            </div>
          </div>

          {/* Animated Graph Preview */}
          <div className="mt-12 relative animate-fade-in-scale stagger-4">
            <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-transparent z-10 pointer-events-none" />
            <div className="rounded-2xl border-2 border-border bg-card overflow-hidden shadow-2xl">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-muted/50">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-destructive/60" />
                  <div className="w-3 h-3 rounded-full bg-warning/60" />
                  <div className="w-3 h-3 rounded-full bg-success/60" />
                </div>
                <span className="text-sm text-muted-foreground ml-2">RepoLens — Code Graph Visualization</span>
              </div>
              <AnimatedGraphPreview />
            </div>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="container py-16 border-t border-border">
        <h2 className="text-2xl md:text-3xl font-bold text-center mb-8">
          Understand Code at a Glance
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <FeatureCard
            icon={GitBranch}
            title="Interactive Graphs"
            description="Visualize files, classes, and functions as interconnected nodes. Click to explore dependencies."
          />
          <FeatureCard
            icon={Brain}
            title="AI-Powered Insights"
            description="Get instant explanations of any code component. Ask questions about architecture and patterns."
          />
          <FeatureCard
            icon={Database}
            title="Deep Analysis"
            description="Parse imports, function calls, and inheritance. Understand how code flows through your system."
          />
        </div>
      </section>

      {/* Tech Stack Section */}
      <section className="container py-16 border-t border-border">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8">
          <div className="text-center md:text-left max-w-md">
            <h2 className="text-2xl md:text-3xl font-bold mb-3">Built for Engineers</h2>
            <p className="text-muted-foreground mb-4">
              RepoLens combines modern technologies to deliver fast, accurate code analysis.
            </p>
            <Button variant="outline" onClick={() => setTechModalOpen(true)}>
              View Technical Architecture
            </Button>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <TechBadge name="FastAPI" description="High-performance API" />
            <TechBadge name="Neo4j" description="Graph database" />
            <TechBadge name="RAG" description="AI retrieval" />
          </div>
        </div>
      </section>

      <TechStackModal open={techModalOpen} onOpenChange={setTechModalOpen} />
    </div>
  );
}

function FeatureCard({ icon: Icon, title, description }: {
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <div className="group p-6 rounded-xl border-2 border-border bg-gradient-to-br from-card to-card/80 shadow-md transition-all duration-300 hover:shadow-xl hover:border-primary/20 hover:-translate-y-1">
      <div className="p-3 rounded-xl bg-primary/10 w-fit mb-4 group-hover:bg-primary/15 transition-colors">
        <Icon className="h-6 w-6 text-primary" />
      </div>
      <h3 className="text-base font-semibold mb-2">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}

function TechBadge({ name, description }: { name: string; description: string }) {
  return (
    <div className="p-4 rounded-xl border border-border bg-gradient-to-br from-muted/40 to-muted/20 text-center min-w-[110px] shadow-sm transition-all duration-200 hover:shadow-md hover:scale-[1.02]">
      <p className="font-mono font-semibold text-sm">{name}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
    </div>
  );
}
