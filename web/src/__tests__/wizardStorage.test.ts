import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readWizardFlags, writeWizardFlags, clearWizardFlags, type WizardFlags } from '../lib/wizardStorage';

describe('wizardStorage', () => {
  const STORAGE_KEY = 'datara.wizard';
  
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();
    
    // Spy on console.warn to suppress expected warnings in tests
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('readWizardFlags', () => {
    it('returns default flags when localStorage is empty', () => {
      const result = readWizardFlags();
      expect(result).toEqual({
        wizardComplete: false,
        wizardSkipped: false,
      });
    });

    it('returns valid flags from localStorage', () => {
      const flags: WizardFlags = { wizardComplete: true, wizardSkipped: false };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(flags));
      
      const result = readWizardFlags();
      expect(result).toEqual(flags);
    });

    it('returns default flags when localStorage has invalid JSON', () => {
      localStorage.setItem(STORAGE_KEY, 'invalid json');
      
      const result = readWizardFlags();
      expect(result).toEqual({
        wizardComplete: false,
        wizardSkipped: false,
      });
      expect(console.warn).toHaveBeenCalled();
    });

    it('returns default flags when localStorage has invalid structure', () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        wizardComplete: 'not-a-boolean',
        wizardSkipped: 123,
      }));
      
      const result = readWizardFlags();
      expect(result).toEqual({
        wizardComplete: false,
        wizardSkipped: false,
      });
      expect(console.warn).toHaveBeenCalled();
    });

    it('returns default flags when localStorage throws', () => {
      // Mock localStorage.getItem to throw
      vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
        throw new Error('Security error');
      });
      
      const result = readWizardFlags();
      expect(result).toEqual({
        wizardComplete: false,
        wizardSkipped: false,
      });
      expect(console.warn).toHaveBeenCalled();
    });

    it('handles partial flags in storage', () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        wizardComplete: true,
        // wizardSkipped missing
      }));
      
      const result = readWizardFlags();
      expect(result).toEqual({
        wizardComplete: false, // Should reset to default
        wizardSkipped: false,
      });
      expect(console.warn).toHaveBeenCalled();
    });
  });

  describe('writeWizardFlags', () => {
    it('writes flags to localStorage', () => {
      writeWizardFlags({ wizardComplete: true });
      
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY)!);
      expect(stored).toEqual({
        wizardComplete: true,
        wizardSkipped: false,
      });
    });

    it('merges with existing flags', () => {
      // Set initial flags
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        wizardComplete: false,
        wizardSkipped: false,
      }));
      
      // Update only wizardComplete
      writeWizardFlags({ wizardComplete: true });
      
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY)!);
      expect(stored).toEqual({
        wizardComplete: true,
        wizardSkipped: false,
      });
    });

    it('swallows errors when localStorage throws', () => {
      // Mock localStorage.setItem to throw
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new Error('Quota exceeded');
      });
      
      // Should not throw
      expect(() => {
        writeWizardFlags({ wizardComplete: true });
      }).not.toThrow();
      
      expect(console.warn).toHaveBeenCalled();
    });

    it('handles read failure during write', () => {
      // Mock read to throw
      vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
        throw new Error('Security error');
      });
      
      // Should not throw
      expect(() => {
        writeWizardFlags({ wizardComplete: true });
      }).not.toThrow();
      
      expect(console.warn).toHaveBeenCalled();
    });
  });

  describe('clearWizardFlags', () => {
    it('removes flags from localStorage', () => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        wizardComplete: true,
        wizardSkipped: false,
      }));
      
      clearWizardFlags();
      
      expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    it('swallows errors when localStorage throws', () => {
      // Mock localStorage.removeItem to throw
      vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
        throw new Error('Security error');
      });
      
      // Should not throw
      expect(() => {
        clearWizardFlags();
      }).not.toThrow();
      
      expect(console.warn).toHaveBeenCalled();
    });
  });
});