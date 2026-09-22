/**
 * Web Vitals tracking for performance monitoring
 * Tracks LCP (Largest Contentful Paint), INP (Interaction to Next Paint), and CLS (Cumulative Layout Shift)
 */

import { onCLS, onINP, onLCP } from 'web-vitals';
import type { Metric } from 'web-vitals';

import { analytics } from './analytics';
import { captureMessage } from './sentry';

function sendToAnalytics(metric: Metric) {
  // Send to PostHog analytics
  analytics.track('web_vital', {
    name: metric.name,
    value: metric.value,
    rating: metric.rating,
    delta: metric.delta,
    id: metric.id,
  });

  // Also send to Sentry
  try {
    captureMessage(`Web Vital: ${metric.name}`, {
      level:
        metric.rating === 'good'
          ? 'info'
          : metric.rating === 'needs-improvement'
          ? 'warning'
          : 'error',
      extra: {
        value: metric.value,
        rating: metric.rating,
        delta: metric.delta,
        id: metric.id,
      },
    });
  } catch {
    // Sentry may not be initialized
  }
}

export function initWebVitals() {
  if (import.meta.env.PROD || import.meta.env.VITE_ENABLE_WEB_VITALS === 'true') {
    // Largest Contentful Paint
    onLCP(sendToAnalytics);

    // Interaction to Next Paint (FID replacement)
    onINP(sendToAnalytics);

    // Cumulative Layout Shift
    onCLS(sendToAnalytics);
  }
}
