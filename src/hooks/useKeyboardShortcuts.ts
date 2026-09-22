import { useEffect, useCallback } from 'react';

interface KeyboardShortcut {
  key: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  shiftKey?: boolean;
  action: () => void;
  description?: string;
}

interface UseKeyboardShortcutsOptions {
  shortcuts: KeyboardShortcut[];
  enabled?: boolean;
}

/**
 * Hook to register global keyboard shortcuts.
 * Automatically handles both Mac (Cmd) and Windows/Linux (Ctrl) modifiers.
 */
export function useKeyboardShortcuts({
  shortcuts,
  enabled = true,
}: UseKeyboardShortcutsOptions) {
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!enabled) return;

      // Don't trigger shortcuts when typing in input fields
      const target = event.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        // Allow Escape to work even in inputs
        if (event.key !== 'Escape') {
          return;
        }
      }

      for (const shortcut of shortcuts) {
        const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase();

        // Check meta/ctrl key (support both for cross-platform)
        const modifierMatch =
          (shortcut.metaKey && (event.metaKey || event.ctrlKey)) ||
          (shortcut.ctrlKey && event.ctrlKey) ||
          (!shortcut.metaKey && !shortcut.ctrlKey);

        const shiftMatch = shortcut.shiftKey ? event.shiftKey : !event.shiftKey;

        if (keyMatch && modifierMatch && shiftMatch) {
          event.preventDefault();
          shortcut.action();
          return;
        }
      }
    },
    [shortcuts, enabled]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

/**
 * Hook for the common Cmd+K / Ctrl+K shortcut to open command palette.
 */
export function useCommandPaletteShortcut(
  onOpen: () => void,
  enabled = true
) {
  useKeyboardShortcuts({
    shortcuts: [
      {
        key: 'k',
        metaKey: true,
        action: onOpen,
        description: 'Open command palette',
      },
    ],
    enabled,
  });
}

/**
 * Hook for the ? key shortcut to open help center.
 */
export function useHelpCenterShortcut(
  onOpen: () => void,
  enabled = true
) {
  useKeyboardShortcuts({
    shortcuts: [
      {
        key: '?',
        action: onOpen,
        description: 'Open help center',
      },
    ],
    enabled,
  });
}
