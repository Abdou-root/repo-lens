import { memo } from 'react';

export const GraphSkeleton = memo(() => {
  return (
    <div className="h-full w-full bg-background p-8 overflow-hidden">
      <div className="h-full w-full relative">
        {/* Simulated graph nodes */}
        <div className="absolute inset-0 grid grid-cols-4 gap-12 p-12">
          {/* Row 1 */}
          <div className="animate-skeleton h-20 rounded-xl bg-muted/20 stagger-1" />
          <div className="animate-skeleton h-20 rounded-xl bg-muted/30 stagger-2" />
          <div className="animate-skeleton h-20 rounded-xl bg-muted/20 stagger-3" />
          <div className="animate-skeleton h-20 rounded-xl bg-muted/30 stagger-4" />

          {/* Row 2 */}
          <div className="animate-skeleton h-24 rounded-xl bg-muted/30 stagger-2" />
          <div className="animate-skeleton h-16 rounded-xl bg-muted/20 stagger-3" />
          <div className="animate-skeleton h-20 rounded-xl bg-muted/30 stagger-4" />
          <div className="animate-skeleton h-20 rounded-xl bg-muted/20 stagger-5" />

          {/* Row 3 */}
          <div className="animate-skeleton h-20 rounded-xl bg-muted/20 stagger-3" />
          <div className="animate-skeleton h-24 rounded-xl bg-muted/30 stagger-4" />
          <div className="animate-skeleton h-16 rounded-xl bg-muted/20 stagger-5" />
          <div className="animate-skeleton h-20 rounded-xl bg-muted/30 stagger-6" />
        </div>

        {/* Simulated edges */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 0 }}>
          <defs>
            <linearGradient id="skeleton-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" style={{ stopColor: 'hsl(var(--muted))', stopOpacity: 0.1 }} />
              <stop offset="50%" style={{ stopColor: 'hsl(var(--muted))', stopOpacity: 0.3 }} />
              <stop offset="100%" style={{ stopColor: 'hsl(var(--muted))', stopOpacity: 0.1 }} />
            </linearGradient>
          </defs>

          {/* Horizontal edges */}
          <path d="M 150 100 L 400 100" stroke="url(#skeleton-gradient)" strokeWidth="2" className="animate-skeleton stagger-1" />
          <path d="M 150 200 L 400 220" stroke="url(#skeleton-gradient)" strokeWidth="2" className="animate-skeleton stagger-2" />
          <path d="M 450 100 L 700 120" stroke="url(#skeleton-gradient)" strokeWidth="2" className="animate-skeleton stagger-3" />
          <path d="M 450 220 L 700 200" stroke="url(#skeleton-gradient)" strokeWidth="2" className="animate-skeleton stagger-4" />

          {/* Vertical connections */}
          <path d="M 250 120 L 250 180" stroke="url(#skeleton-gradient)" strokeWidth="2" className="animate-skeleton stagger-2" />
          <path d="M 575 140 L 575 180" stroke="url(#skeleton-gradient)" strokeWidth="2" className="animate-skeleton stagger-3" />
        </svg>

        {/* Overlay message */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center space-y-3 bg-background/80 backdrop-blur-sm px-8 py-6 rounded-2xl border border-border shadow-lg">
            <div className="flex items-center justify-center gap-3">
              <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
              <div className="h-2 w-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: '0.2s' }} />
              <div className="h-2 w-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: '0.4s' }} />
            </div>
            <p className="text-sm font-medium text-muted-foreground">
              Building code graph visualization...
            </p>
          </div>
        </div>
      </div>
    </div>
  );
});

GraphSkeleton.displayName = 'GraphSkeleton';
