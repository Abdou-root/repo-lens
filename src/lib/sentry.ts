import * as Sentry from '@sentry/react';

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;
const ENVIRONMENT = import.meta.env.MODE || 'development';

export function initSentry() {
  // Only initialize Sentry if DSN is provided
  if (!SENTRY_DSN) {
    // Silently skip initialization in development if DSN not provided
    return;
  }

  Sentry.init({
    dsn: SENTRY_DSN,
    environment: ENVIRONMENT,

    // Performance Monitoring
    integrations: [
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
      }),
    ],

    // Set tracesSampleRate to 1.0 to capture 100% of transactions for performance monitoring.
    // We recommend adjusting this value in production
    tracesSampleRate: ENVIRONMENT === 'production' ? 0.1 : 1.0,

    // Capture Replay for 10% of all sessions,
    // plus for 100% of sessions with an error
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,

    // Filter out common errors
    ignoreErrors: [
      // Browser extensions
      'top.GLOBALS',
      'canvas.contentDocument',
      'MyApp_RemoveAllHighlights',
      'atomicFindClose',
      // Network errors
      'NetworkError',
      'Failed to fetch',
      'Load failed',
      // Random plugins/extensions
      'Can\'t find variable: ZiteReader',
      'jigsaw is not defined',
      'ComboSearch is not defined',
    ],

    beforeSend(event, hint) {
      // Filter out errors from browser extensions
      if (event.exception) {
        const error = hint.originalException;
        if (
          error &&
          typeof error === 'object' &&
          'message' in error &&
          typeof error.message === 'string'
        ) {
          if (error.message.match(/chrome-extension:\/\//i)) {
            return null;
          }
        }
      }

      // Add user context if available
      const user = localStorage.getItem('repolens_user');
      if (user) {
        try {
          const userData = JSON.parse(user);
          event.user = {
            id: userData.id,
            email: userData.email,
            username: userData.name,
          };
        } catch (e) {
          if (!import.meta.env.PROD) {
            console.error('Failed to parse user data for Sentry:', e);
          }
        }
      }

      return event;
    },
  });

  if (!import.meta.env.PROD) {
    console.log('Sentry initialized successfully');
  }
}

export function captureError(error: Error, context?: Record<string, any>) {
  if (SENTRY_DSN) {
    Sentry.captureException(error, {
      contexts: context ? { extra: context } : undefined,
    });
  } else {
    if (!import.meta.env.PROD) {
      console.error('Error (Sentry not configured):', error, context);
    }
  }
}

export function captureMessage(message: string, level: Sentry.SeverityLevel = 'info') {
  if (SENTRY_DSN) {
    Sentry.captureMessage(message, level);
  } else {
    if (!import.meta.env.PROD) {
      console.log(`[${level}] ${message}`);
    }
  }
}

export function setUserContext(user: { id: string; email?: string; name?: string }) {
  if (SENTRY_DSN) {
    Sentry.setUser({
      id: user.id,
      email: user.email,
      username: user.name,
    });
  }
}

export function clearUserContext() {
  if (SENTRY_DSN) {
    Sentry.setUser(null);
  }
}

export { Sentry };
