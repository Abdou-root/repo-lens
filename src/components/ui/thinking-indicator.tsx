import { useState, useEffect } from 'react';

const THINKING_WORDS = [
  'Thinking',
  'Analyzing',
  'Generating',
  'Processing',
  'Reasoning',
];

export function ThinkingIndicator() {
  const [wordIndex, setWordIndex] = useState(0);
  const [isTransitioning, setIsTransitioning] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setIsTransitioning(true);
      setTimeout(() => {
        setWordIndex((prev) => (prev + 1) % THINKING_WORDS.length);
        setIsTransitioning(false);
      }, 200);
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center gap-3 py-3 px-4 rounded-2xl bg-gradient-to-r from-primary/5 via-primary/10 to-primary/5 border border-primary/20 animate-fade-in-up relative overflow-hidden">
      {/* Shimmer effect overlay */}
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-shimmer" />

      {/* Bouncing dots */}
      <div className="flex gap-1.5 relative z-10">
        <span
          className="w-2 h-2 bg-primary rounded-full animate-bounce"
          style={{ animationDelay: '0ms', animationDuration: '600ms' }}
        />
        <span
          className="w-2 h-2 bg-primary rounded-full animate-bounce"
          style={{ animationDelay: '150ms', animationDuration: '600ms' }}
        />
        <span
          className="w-2 h-2 bg-primary rounded-full animate-bounce"
          style={{ animationDelay: '300ms', animationDuration: '600ms' }}
        />
      </div>

      {/* Rotating text */}
      <span
        className={`text-sm font-medium text-primary relative z-10 transition-all duration-200 ${
          isTransitioning ? 'opacity-0 translate-y-2' : 'opacity-100 translate-y-0'
        }`}
      >
        {THINKING_WORDS[wordIndex]}...
      </span>
    </div>
  );
}
