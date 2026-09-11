import { useEffect, useRef, type RefObject } from 'react';

/**
 * A minimal focus trap for modal dialogs.
 *
 * - On mount, saves the current `document.activeElement`.
 * - Focuses the provided initial element (should be the first focusable element).
 * - On keydown in the dialog: Escape triggers onEscape, Tab/Shift+Tab wraps focus
 *   among visible focusable elements (filter `offsetParent !== null`).
 * - On unmount, restores focus to the saved element.
 *
 * @param elementRef - Ref to the dialog element to trap focus within.
 * @param initialFocusRef - Ref to the element to focus first (usually the Skip button).
 * @param onEscape - Callback for Escape key (should skip/close the wizard).
 */
export function useFocusTrap(
  elementRef: RefObject<HTMLElement | null>,
  initialFocusRef: RefObject<HTMLElement | null>,
  onEscape: () => void
) {
  const savedFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    // Save current focus
    savedFocusRef.current = document.activeElement as HTMLElement;

    // Focus the initial element
    const initialFocusElement = initialFocusRef.current;
    if (initialFocusElement) {
      initialFocusElement.focus();
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (!element.contains(e.target as Node)) {
        return;
      }

      // Escape → close/skip
      if (e.key === 'Escape') {
        e.preventDefault();
        onEscape();
        return;
      }

      // Tab trapping
      if (e.key === 'Tab') {
        const focusableElements = Array.from(
          element.querySelectorAll<HTMLElement>(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => {
          // Only include visible elements
          return el.offsetParent !== null && !el.hasAttribute('disabled');
        });

        if (focusableElements.length === 0) {
          e.preventDefault();
          return;
        }

        const first = focusableElements[0];
        const last = focusableElements[focusableElements.length - 1];
        const current = document.activeElement as HTMLElement;

        // If Shift+Tab and focus is on first element, wrap to last
        if (e.shiftKey && current === first) {
          e.preventDefault();
          last.focus();
        }
        // If Tab and focus is on last element, wrap to first
        else if (!e.shiftKey && current === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    element.addEventListener('keydown', handleKeyDown);

    return () => {
      element.removeEventListener('keydown', handleKeyDown);
      // Restore focus
      if (savedFocusRef.current && savedFocusRef.current.focus) {
        savedFocusRef.current.focus();
      }
    };
    // Refs are stable objects; re-attach only when the escape callback changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onEscape]);
}
