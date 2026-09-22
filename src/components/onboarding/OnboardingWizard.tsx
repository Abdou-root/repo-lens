import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useOnboarding } from '@/contexts/OnboardingContext';
import { Check, ArrowRight, ArrowLeft, Sparkles, Search, MessageSquare, Zap, X } from 'lucide-react';
import { toast } from 'sonner';

interface OnboardingWizardProps {
  open: boolean;
  onClose: () => void;
}

export function OnboardingWizard({ open, onClose }: OnboardingWizardProps) {
  const { currentStep, totalSteps, setStep, completeOnboarding, skipOnboarding } = useOnboarding();
  const [repoUrl, setRepoUrl] = useState('');
  const [dontShowAgain, setDontShowAgain] = useState(false);

  const handleNext = () => {
    if (currentStep < totalSteps - 1) {
      setStep(currentStep + 1);
    } else {
      handleComplete();
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setStep(currentStep - 1);
    }
  };

  const handleComplete = () => {
    completeOnboarding();
    onClose();
    toast.success('Welcome to RepoLens! Start exploring your code.');
  };

  const handleSkip = () => {
    if (dontShowAgain) {
      skipOnboarding();
    }
    onClose();
  };

  const handleAddRepo = () => {
    if (repoUrl.trim()) {
      // Validate GitHub URL
      const githubUrlPattern = /^https?:\/\/(www\.)?github\.com\/[\w-]+\/[\w.-]+/;
      if (!githubUrlPattern.test(repoUrl)) {
        toast.error('Please enter a valid GitHub repository URL');
        return;
      }

      // Move to next step
      toast.success('Repository URL validated! Proceeding...');
      handleNext();
    } else {
      toast.error('Please enter a repository URL');
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleSkip}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-2xl">
              {currentStep === 0 && 'Welcome to RepoLens'}
              {currentStep === 1 && 'Add Your First Repository'}
              {currentStep === 2 && 'Understanding the Graph'}
              {currentStep === 3 && 'AI-Powered Insights'}
              {currentStep === 4 && 'Ready to Explore!'}
            </DialogTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSkip}
              className="h-8 w-8 p-0"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
          <DialogDescription>
            Step {currentStep + 1} of {totalSteps}
          </DialogDescription>
        </DialogHeader>

        <div className="py-6">
          {/* Step 0: Welcome */}
          {currentStep === 0 && (
            <div className="space-y-4 text-center">
              <div className="flex justify-center">
                <div className="h-20 w-20 rounded-full bg-primary/10 flex items-center justify-center">
                  <Sparkles className="h-10 w-10 text-primary" />
                </div>
              </div>
              <h3 className="text-xl font-semibold">Visualize Your Codebase</h3>
              <p className="text-muted-foreground max-w-md mx-auto">
                RepoLens transforms your code into interactive knowledge graphs, making it easy to understand complex dependencies, discover insights, and navigate your projects with AI assistance.
              </p>
              <div className="grid grid-cols-3 gap-4 pt-4">
                <div className="p-4 border rounded-lg">
                  <div className="h-10 w-10 rounded-full bg-chart-1/10 flex items-center justify-center mx-auto mb-2">
                    <Zap className="h-5 w-5 text-chart-1" />
                  </div>
                  <p className="text-sm font-medium">Interactive Graphs</p>
                  <p className="text-xs text-muted-foreground mt-1">Explore code relationships visually</p>
                </div>
                <div className="p-4 border rounded-lg">
                  <div className="h-10 w-10 rounded-full bg-chart-2/10 flex items-center justify-center mx-auto mb-2">
                    <Search className="h-5 w-5 text-chart-2" />
                  </div>
                  <p className="text-sm font-medium">Smart Search</p>
                  <p className="text-xs text-muted-foreground mt-1">Find functions, classes instantly</p>
                </div>
                <div className="p-4 border rounded-lg">
                  <div className="h-10 w-10 rounded-full bg-chart-3/10 flex items-center justify-center mx-auto mb-2">
                    <MessageSquare className="h-5 w-5 text-chart-3" />
                  </div>
                  <p className="text-sm font-medium">AI Chat</p>
                  <p className="text-xs text-muted-foreground mt-1">Ask questions about your code</p>
                </div>
              </div>
            </div>
          )}

          {/* Step 1: Add Repository */}
          {currentStep === 1 && (
            <div className="space-y-4">
              <div className="text-center mb-6">
                <h3 className="text-lg font-semibold mb-2">Add Your First Repository</h3>
                <p className="text-muted-foreground text-sm">
                  Enter a GitHub repository URL to get started. We'll analyze the code and build an interactive graph.
                </p>
              </div>
              <div className="space-y-3">
                <label className="text-sm font-medium">GitHub Repository URL</label>
                <Input
                  placeholder="https://github.com/username/repository"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddRepo()}
                  className="text-base"
                />
                <p className="text-xs text-muted-foreground">
                  Example: https://github.com/facebook/react
                </p>
              </div>
              <div className="bg-muted/50 p-4 rounded-lg mt-4">
                <p className="text-sm font-medium mb-2">What happens next?</p>
                <ul className="text-sm text-muted-foreground space-y-1">
                  <li className="flex items-start gap-2">
                    <Check className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                    <span>We'll clone and analyze your repository</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                    <span>Extract files, classes, functions, and dependencies</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                    <span>Build an interactive knowledge graph</span>
                  </li>
                </ul>
              </div>
            </div>
          )}

          {/* Step 2: Graph Tutorial */}
          {currentStep === 2 && (
            <div className="space-y-4">
              <div className="text-center mb-4">
                <h3 className="text-lg font-semibold mb-2">Navigating the Graph</h3>
                <p className="text-muted-foreground text-sm">
                  Learn how to interact with the code graph
                </p>
              </div>
              <div className="grid gap-4">
                <div className="flex gap-3 items-start p-3 border rounded-lg">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-1">
                    <span className="text-sm font-bold text-primary">1</span>
                  </div>
                  <div>
                    <p className="font-medium text-sm">Click a node to explore</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Click any file, class, or function to see its details, connections, and code
                    </p>
                  </div>
                </div>
                <div className="flex gap-3 items-start p-3 border rounded-lg">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-1">
                    <span className="text-sm font-bold text-primary">2</span>
                  </div>
                  <div>
                    <p className="font-medium text-sm">Zoom and pan</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Use scroll to zoom, click and drag to pan. Pinch to zoom on mobile
                    </p>
                  </div>
                </div>
                <div className="flex gap-3 items-start p-3 border rounded-lg">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-1">
                    <span className="text-sm font-bold text-primary">3</span>
                  </div>
                  <div>
                    <p className="font-medium text-sm">Search and filter</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Use the search bar to find specific files, or filter by type (files, classes, functions)
                    </p>
                  </div>
                </div>
                <div className="flex gap-3 items-start p-3 border rounded-lg">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-1">
                    <span className="text-sm font-bold text-primary">4</span>
                  </div>
                  <div>
                    <p className="font-medium text-sm">Switch views</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Toggle between folder view (hierarchical) and flat view (all nodes)
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Step 3: AI Features */}
          {currentStep === 3 && (
            <div className="space-y-4">
              <div className="text-center mb-4">
                <h3 className="text-lg font-semibold mb-2">AI-Powered Features</h3>
                <p className="text-muted-foreground text-sm">
                  Get intelligent insights and answers about your code
                </p>
              </div>
              <div className="space-y-3">
                <div className="p-4 border rounded-lg bg-gradient-to-br from-chart-1/5 to-transparent">
                  <div className="flex items-start gap-3">
                    <MessageSquare className="h-5 w-5 text-chart-1 mt-1" />
                    <div>
                      <p className="font-medium text-sm mb-1">AI Chat</p>
                      <p className="text-xs text-muted-foreground mb-2">
                        Ask natural language questions about your codebase
                      </p>
                      <div className="bg-background/80 p-2 rounded text-xs font-mono">
                        "Where is user authentication handled?"
                      </div>
                    </div>
                  </div>
                </div>
                <div className="p-4 border rounded-lg bg-gradient-to-br from-chart-2/5 to-transparent">
                  <div className="flex items-start gap-3">
                    <Sparkles className="h-5 w-5 text-chart-2 mt-1" />
                    <div>
                      <p className="font-medium text-sm mb-1">Smart Insights</p>
                      <p className="text-xs text-muted-foreground mb-2">
                        Discover complexity hotspots, entry points, and architectural hubs
                      </p>
                      <div className="bg-background/80 p-2 rounded text-xs">
                        Automatically detects files with high complexity or many connections
                      </div>
                    </div>
                  </div>
                </div>
                <div className="p-4 border rounded-lg bg-gradient-to-br from-chart-3/5 to-transparent">
                  <div className="flex items-start gap-3">
                    <Zap className="h-5 w-5 text-chart-3 mt-1" />
                    <div>
                      <p className="font-medium text-sm mb-1">Command Palette</p>
                      <p className="text-xs text-muted-foreground mb-2">
                        Quick access to all features with keyboard shortcuts
                      </p>
                      <div className="bg-background/80 p-2 rounded text-xs">
                        Press <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">⌘K</kbd> to open
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Ready */}
          {currentStep === 4 && (
            <div className="space-y-4 text-center">
              <div className="flex justify-center">
                <div className="h-20 w-20 rounded-full bg-primary/10 flex items-center justify-center">
                  <Check className="h-10 w-10 text-primary" />
                </div>
              </div>
              <h3 className="text-xl font-semibold">You're All Set!</h3>
              <p className="text-muted-foreground max-w-md mx-auto">
                You're ready to start exploring your codebase. Need help? Press <kbd className="px-2 py-1 bg-muted rounded text-xs">?</kbd> anytime to access the help center.
              </p>
              <div className="bg-muted/50 p-4 rounded-lg mt-4">
                <p className="text-sm font-medium mb-2">Quick Tips:</p>
                <ul className="text-sm text-muted-foreground space-y-1 text-left">
                  <li className="flex items-start gap-2">
                    <Check className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                    <span>Use the search bar to quickly find specific files or functions</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                    <span>Click the Insights button to discover complexity hotspots</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                    <span>Open AI Chat to ask questions about your code</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
                    <span>Export your graph as a PNG for documentation or sharing</span>
                  </li>
                </ul>
              </div>
              <div className="flex items-center justify-center gap-2 pt-2">
                <input
                  type="checkbox"
                  id="dont-show-again"
                  checked={dontShowAgain}
                  onChange={(e) => setDontShowAgain(e.target.checked)}
                  className="h-4 w-4 rounded border-input"
                />
                <label htmlFor="dont-show-again" className="text-sm text-muted-foreground cursor-pointer">
                  Don't show this again
                </label>
              </div>
            </div>
          )}
        </div>

        {/* Progress Indicator */}
        <div className="flex items-center justify-center gap-2 pb-4">
          {Array.from({ length: totalSteps }).map((_, idx) => (
            <div
              key={idx}
              className={`h-2 rounded-full transition-all ${
                idx === currentStep
                  ? 'w-8 bg-primary'
                  : idx < currentStep
                  ? 'w-2 bg-primary/50'
                  : 'w-2 bg-muted'
              }`}
            />
          ))}
        </div>

        {/* Navigation Buttons */}
        <div className="flex items-center justify-between border-t pt-4">
          <Button
            variant="ghost"
            onClick={handleSkip}
            size="sm"
          >
            Skip Tutorial
          </Button>
          <div className="flex gap-2">
            {currentStep > 0 && (
              <Button
                variant="outline"
                onClick={handlePrev}
                size="sm"
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Previous
              </Button>
            )}
            <Button
              onClick={currentStep === 1 ? handleAddRepo : handleNext}
              size="sm"
            >
              {currentStep === totalSteps - 1 ? 'Get Started' : 'Next'}
              {currentStep !== totalSteps - 1 && <ArrowRight className="h-4 w-4 ml-2" />}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
