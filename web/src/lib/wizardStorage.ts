export interface WizardFlags {
  wizardComplete: boolean;
  wizardSkipped: boolean;
}

const STORAGE_KEY = 'datara.wizard';

const DEFAULT_FLAGS: WizardFlags = {
  wizardComplete: false,
  wizardSkipped: false,
};

/**
 * Safely read wizard flags from localStorage.
 * If storage is unavailable, throws, or contains invalid data,
 * returns default values (both flags false → show wizard).
 */
export function readWizardFlags(): WizardFlags {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_FLAGS };
    }
    
    const parsed = JSON.parse(raw);
    
    // Basic validation
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      typeof parsed.wizardComplete === 'boolean' &&
      typeof parsed.wizardSkipped === 'boolean'
    ) {
      return {
        wizardComplete: parsed.wizardComplete,
        wizardSkipped: parsed.wizardSkipped,
      };
    } else {
      // Invalid data in storage — treat as unreadable
      console.warn('Invalid wizard flags in localStorage:', parsed);
      return { ...DEFAULT_FLAGS };
    }
  } catch (err) {
    // localStorage unavailable (private mode, security settings)
    // or JSON parse error — default to showing wizard
    console.warn('Failed to read wizard flags:', err);
    return { ...DEFAULT_FLAGS };
  }
}

/**
 * Write wizard flags to localStorage.
 * Swallows any errors (fail silently).
 */
export function writeWizardFlags(partial: Partial<WizardFlags>): void {
  try {
    const current = readWizardFlags();
    const updated = { ...current, ...partial };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch (err) {
    // Swallow errors — persistence is best-effort
    console.warn('Failed to write wizard flags:', err);
  }
}

/**
 * Clear wizard flags from localStorage.
 * Used in tests or for debugging.
 */
export function clearWizardFlags(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    // Swallow errors
    console.warn('Failed to clear wizard flags:', err);
  }
}