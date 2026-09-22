import DOMPurify from 'dompurify';

/**
 * Sanitize HTML content to prevent XSS attacks
 *
 * @param dirty - Potentially unsafe HTML string
 * @param options - Optional DOMPurify configuration
 * @returns Sanitized HTML string safe for rendering
 */
export function sanitizeHTML(
  dirty: string,
  options?: DOMPurify.Config
): string {
  const defaultConfig: DOMPurify.Config = {
    ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br', 'code', 'pre'],
    ALLOWED_ATTR: ['href', 'target', 'rel'],
    ALLOW_DATA_ATTR: false,
  };

  return DOMPurify.sanitize(dirty, { ...defaultConfig, ...options });
}

/**
 * Sanitize plain text - strips all HTML tags
 *
 * @param dirty - Potentially unsafe string
 * @returns Plain text with all HTML stripped
 */
export function sanitizeText(dirty: string): string {
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: [],
    ALLOWED_ATTR: [],
  });
}

/**
 * Sanitize user input for display in UI
 * Allows only basic formatting tags
 *
 * @param dirty - User input string
 * @returns Sanitized string safe for display
 */
export function sanitizeUserInput(dirty: string): string {
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: ['b', 'i', 'em', 'strong'],
    ALLOWED_ATTR: [],
  });
}
