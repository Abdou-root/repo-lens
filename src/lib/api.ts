/**
 * Centralized API client for RepoLens frontend.
 *
 * Handles:
 * - Base URL configuration from environment
 * - Cookie-based authentication (httpOnly cookies)
 * - CSRF token protection
 * - Server-Sent Events (SSE) streaming
 * - Request timeout
 * - Automatic retry with exponential backoff
 * - Error handling with meaningful messages
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Default timeout in milliseconds
const DEFAULT_TIMEOUT = 30000; // 30 seconds

// Retry configuration
const MAX_RETRIES = 3;
const RETRY_DELAYS = [1000, 3000, 5000]; // 1s, 3s, 5s

// HTTP status codes that should trigger retry
const RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504];

interface ApiError extends Error {
  status?: number;
  statusText?: string;
  isRetryable?: boolean;
}

/**
 * Create a timeout signal that aborts after specified milliseconds
 */
function createTimeoutSignal(timeoutMs: number): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), timeoutMs);
  return controller.signal;
}

/**
 * Combine multiple abort signals into one
 */
function combineSignals(...signals: (AbortSignal | undefined)[]): AbortSignal {
  const controller = new AbortController();

  for (const signal of signals) {
    if (signal) {
      if (signal.aborted) {
        controller.abort();
        break;
      }
      signal.addEventListener('abort', () => controller.abort());
    }
  }

  return controller.signal;
}

/**
 * Create an ApiError with additional context
 */
function createApiError(message: string, status?: number, statusText?: string): ApiError {
  const error: ApiError = new Error(message);
  error.status = status;
  error.statusText = statusText;
  error.isRetryable = status ? RETRYABLE_STATUS_CODES.includes(status) : false;
  return error;
}

/**
 * Get user-friendly error message based on status code
 */
function getErrorMessage(status: number, statusText: string): string {
  switch (status) {
    case 400:
      return 'Invalid request. Please check your input.';
    case 401:
      return 'Your session has expired. Please log in again.';
    case 403:
      return 'You do not have permission to perform this action.';
    case 404:
      return 'The requested resource was not found.';
    case 408:
      return 'Request timed out. Please try again.';
    case 429:
      return 'Too many requests. Please wait a moment and try again.';
    case 500:
      return 'Server error. Please try again later.';
    case 502:
    case 503:
    case 504:
      return 'Service temporarily unavailable. Please try again.';
    default:
      return `API Error: ${status} ${statusText}`;
  }
}

/**
 * Wait for specified milliseconds
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

class ApiClient {
  /**
   * Get CSRF token from cookie.
   * The backend sets a non-httpOnly CSRF cookie that we can read.
   */
  private getCsrfToken(): string | null {
    const name = 'csrf_token=';
    const decodedCookie = decodeURIComponent(document.cookie);
    const ca = decodedCookie.split(';');

    for (let i = 0; i < ca.length; i++) {
      let c = ca[i];
      while (c.charAt(0) === ' ') {
        c = c.substring(1);
      }
      if (c.indexOf(name) === 0) {
        return c.substring(name.length, c.length);
      }
    }
    return null;
  }

  /**
   * Get headers with Authorization and optional CSRF token.
   */
  private getHeaders(includeCSRF: boolean = false): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    // Add Authorization header with Bearer token from localStorage
    const accessToken = localStorage.getItem('repolens_access_token');
    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }

    // Add CSRF token for state-changing operations (defense in depth)
    if (includeCSRF) {
      const csrfToken = this.getCsrfToken();
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }
    }

    return headers;
  }

  /**
   * Execute fetch with timeout and optional retry
   */
  private async fetchWithRetry(
    url: string,
    options: RequestInit,
    {
      timeout = DEFAULT_TIMEOUT,
      retries = 0,
      retryOnlyGet = true,
    }: {
      timeout?: number;
      retries?: number;
      retryOnlyGet?: boolean;
    } = {}
  ): Promise<Response> {
    const method = options.method || 'GET';
    const shouldRetry = retries > 0 && (!retryOnlyGet || method === 'GET');
    let lastError: ApiError | null = null;

    const maxAttempts = shouldRetry ? Math.min(retries, MAX_RETRIES) : 1;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        // Create timeout signal
        const timeoutSignal = createTimeoutSignal(timeout);

        // Combine with user-provided signal if any
        const combinedSignal = options.signal
          ? combineSignals(timeoutSignal, options.signal)
          : timeoutSignal;

        const response = await fetch(url, {
          ...options,
          signal: combinedSignal,
        });

        // Check if response indicates we should retry
        if (!response.ok && RETRYABLE_STATUS_CODES.includes(response.status) && attempt < maxAttempts - 1) {
          lastError = createApiError(
            getErrorMessage(response.status, response.statusText),
            response.status,
            response.statusText
          );

          // Wait before retry with exponential backoff
          const delay = RETRY_DELAYS[Math.min(attempt, RETRY_DELAYS.length - 1)];
          if (!import.meta.env.PROD) {
            console.log(`Retrying request to ${url} in ${delay}ms (attempt ${attempt + 2}/${maxAttempts})`);
          }
          await sleep(delay);
          continue;
        }

        return response;
      } catch (error) {
        // Handle abort errors
        if (error instanceof Error && error.name === 'AbortError') {
          // Check if it was a timeout or user abort
          if (options.signal?.aborted) {
            throw error; // User aborted, don't retry
          }
          // Timeout - may retry
          lastError = createApiError('Request timed out', 408, 'Timeout');
          lastError.isRetryable = true;
        } else if (error instanceof TypeError && error.message.includes('fetch')) {
          // Network error
          lastError = createApiError('Network error. Please check your connection.', 0, 'Network Error');
          lastError.isRetryable = true;
        } else {
          throw error;
        }

        // Retry on network/timeout errors
        if (attempt < maxAttempts - 1) {
          const delay = RETRY_DELAYS[Math.min(attempt, RETRY_DELAYS.length - 1)];
          if (!import.meta.env.PROD) {
            console.log(`Retrying request to ${url} in ${delay}ms (attempt ${attempt + 2}/${maxAttempts})`);
          }
          await sleep(delay);
          continue;
        }
      }
    }

    // All retries exhausted
    throw lastError || createApiError('Request failed after retries');
  }

  /**
   * GET request with timeout and retry
   */
  async get<T>(
    path: string,
    options?: {
      signal?: AbortSignal;
      timeout?: number;
      retries?: number;
    }
  ): Promise<T> {
    const response = await this.fetchWithRetry(
      `${API_BASE_URL}${path}`,
      {
        method: 'GET',
        headers: this.getHeaders(false),
                signal: options?.signal,
      },
      {
        timeout: options?.timeout ?? DEFAULT_TIMEOUT,
        retries: options?.retries ?? MAX_RETRIES,
      }
    );

    if (!response.ok) {
      throw createApiError(
        getErrorMessage(response.status, response.statusText),
        response.status,
        response.statusText
      );
    }

    return response.json();
  }

  /**
   * POST request with CSRF protection and timeout
   */
  async post<T>(
    path: string,
    body?: any,
    options?: {
      timeout?: number;
    }
  ): Promise<T> {
    const response = await this.fetchWithRetry(
      `${API_BASE_URL}${path}`,
      {
        method: 'POST',
        headers: this.getHeaders(true),
                body: body ? JSON.stringify(body) : undefined,
      },
      {
        timeout: options?.timeout ?? DEFAULT_TIMEOUT,
        retries: 0, // Don't retry POST by default (not idempotent)
      }
    );

    if (!response.ok) {
      throw createApiError(
        getErrorMessage(response.status, response.statusText),
        response.status,
        response.statusText
      );
    }

    return response.json();
  }

  /**
   * DELETE request with CSRF protection and timeout
   */
  async delete<T>(
    path: string,
    options?: {
      timeout?: number;
    }
  ): Promise<T> {
    const response = await this.fetchWithRetry(
      `${API_BASE_URL}${path}`,
      {
        method: 'DELETE',
        headers: this.getHeaders(true),
              },
      {
        timeout: options?.timeout ?? DEFAULT_TIMEOUT,
        retries: 0, // Don't retry DELETE by default
      }
    );

    if (!response.ok) {
      throw createApiError(
        getErrorMessage(response.status, response.statusText),
        response.status,
        response.statusText
      );
    }

    return response.json();
  }

  /**
   * Server-Sent Events (SSE) stream helper with timeout
   *
   * @param path - API endpoint path
   * @param body - Request body (optional)
   * @param onMessage - Callback for each SSE message
   * @param onError - Callback for errors (optional)
   * @param onComplete - Callback when stream completes (optional)
   * @param signal - AbortSignal to cancel the stream (optional)
   * @param timeout - Request timeout in ms (default: 5 minutes for streaming)
   */
  async streamSSE(
    path: string,
    body: any,
    onMessage: (data: any) => void,
    onError?: (error: Error) => void,
    onComplete?: () => void,
    signal?: AbortSignal,
    timeout: number = 300000 // 5 minutes for streaming
  ): Promise<void> {
    try {
      // Create timeout signal
      const timeoutSignal = createTimeoutSignal(timeout);
      const combinedSignal = signal
        ? combineSignals(timeoutSignal, signal)
        : timeoutSignal;

      const response = await fetch(`${API_BASE_URL}${path}`, {
        method: 'POST',
        headers: this.getHeaders(true),
                body: JSON.stringify(body),
        signal: combinedSignal,
      });

      if (!response.ok) {
        throw createApiError(
          getErrorMessage(response.status, response.statusText),
          response.status,
          response.statusText
        );
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Response body is not readable');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          if (onComplete) onComplete();
          break;
        }

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true });

        // Process complete lines
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onMessage(data);
            } catch (e) {
              if (!import.meta.env.PROD) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }
        }
      }
    } catch (error) {
      // Ignore abort errors
      if (error instanceof Error && error.name === 'AbortError') {
        return;
      }

      if (onError) {
        onError(error as Error);
      } else {
        if (!import.meta.env.PROD) {
          console.error('SSE Stream Error:', error);
        }
      }
    }
  }

  /**
   * Create an EventSource for SSE GET requests
   * (for endpoints that use GET instead of POST)
   */
  createEventSource(path: string): EventSource {
    const url = `${API_BASE_URL}${path}`;
    return new EventSource(url);
  }

  /**
   * Refresh access token using refresh token
   * Returns true if refresh succeeded, false otherwise
   */
  async refreshAccessToken(): Promise<boolean> {
    const refreshToken = localStorage.getItem('repolens_refresh_token');
    if (!refreshToken) {
      return false;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        // Refresh failed - clear tokens
        localStorage.removeItem('repolens_access_token');
        localStorage.removeItem('repolens_refresh_token');
        localStorage.removeItem('repolens_user');
        return false;
      }

      const data = await response.json();
      localStorage.setItem('repolens_access_token', data.access_token);
      return true;
    } catch {
      return false;
    }
  }
}

// Export singleton instance
export const api = new ApiClient();
