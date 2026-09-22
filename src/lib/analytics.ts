/**
 * Product analytics integration for RepoLens
 * Uses PostHog for event tracking
 */

const POSTHOG_API_KEY = import.meta.env.VITE_POSTHOG_API_KEY;
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || 'https://app.posthog.com';

interface AnalyticsEvent {
  event: string;
  properties?: Record<string, any>;
}

class Analytics {
  private posthog: any = null;
  private initialized = false;

  constructor() {
    if (POSTHOG_API_KEY && typeof window !== 'undefined') {
      this.init();
    }
  }

  private async init() {
    if (this.initialized) return;

    try {
      // Dynamically import posthog-js
      const posthog = (await import('posthog-js')).default;
      
      posthog.init(POSTHOG_API_KEY, {
        api_host: POSTHOG_HOST,
        autocapture: false, // Disable automatic capture for privacy
        capture_pageview: false, // We'll track pageviews manually
        loaded: (posthog) => {
          this.posthog = posthog;
          this.initialized = true;
        }
      });
    } catch (error) {
      if (!import.meta.env.PROD) {
        console.error('Failed to initialize PostHog:', error);
      }
    }
  }

  async track(event: string, properties?: Record<string, any>) {
    if (!this.initialized) {
      await this.init();
    }

    if (!this.posthog) return;

    try {
      this.posthog.capture(event, properties);
    } catch (error) {
      if (!import.meta.env.PROD) {
        console.error('Failed to track event:', error);
      }
    }
  }

  identify(userId: string, traits?: Record<string, any>) {
    if (!this.posthog) return;

    try {
      this.posthog.identify(userId, traits);
    } catch (error) {
      if (!import.meta.env.PROD) {
        console.error('Failed to identify user:', error);
      }
    }
  }

  reset() {
    if (!this.posthog) return;

    try {
      this.posthog.reset();
    } catch (error) {
      if (!import.meta.env.PROD) {
        console.error('Failed to reset analytics:', error);
      }
    }
  }

  page(name?: string, properties?: Record<string, any>) {
    if (!this.posthog) return;

    try {
      this.posthog.capture('$pageview', {
        page_name: name || window.location.pathname,
        ...properties
      });
    } catch (error) {
      if (!import.meta.env.PROD) {
        console.error('Failed to track pageview:', error);
      }
    }
  }
}

// Export singleton instance
export const analytics = new Analytics();

// Helper functions for common events
export const trackEvent = (event: string, properties?: Record<string, any>) => {
  analytics.track(event, properties);
};

export const trackPageView = (pageName?: string, properties?: Record<string, any>) => {
  analytics.page(pageName, properties);
};

// Common event names
export const Events = {
  REPO_CREATED: 'repo_created',
  REPO_VIEWED: 'repo_viewed',
  GRAPH_VIEWED: 'graph_viewed',
  GRAPH_EXPORTED: 'graph_exported',
  CHAT_MESSAGE_SENT: 'chat_message_sent',
  SEARCH_PERFORMED: 'search_performed',
  INSIGHTS_VIEWED: 'insights_viewed',
  COMMAND_PALETTE_OPENED: 'command_palette_opened',
  NODE_CLICKED: 'node_clicked',
  FILTER_APPLIED: 'filter_applied',
  FOCUS_MODE_CHANGED: 'focus_mode_changed',
} as const;

