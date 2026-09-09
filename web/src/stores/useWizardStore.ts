import { create } from 'zustand';
import { readWizardFlags } from '../lib/wizardStorage';

interface WizardUiState {
  open: boolean;
  engaged: boolean;
  manual: boolean;
  dismissed: boolean;
  openWizard: (manual?: boolean) => void;
  closeWizard: (dismiss?: boolean) => void;
  setEngaged: () => void;
}

export const useWizardStore = create<WizardUiState>((set) => {
  // Initialize dismissed state from localStorage
  const flags = readWizardFlags();
  const initiallyDismissed = flags.wizardComplete || flags.wizardSkipped;
  
  return {
    open: false,
    engaged: false,
    manual: false,
    dismissed: initiallyDismissed,
    
    openWizard: (manual = false) => {
      set((state) => {
        // Don't open if dismissed (skipped or completed)
        if (state.dismissed) {
          return state;
        }
        
        return {
          open: true,
          manual: manual,
          // Reset engaged when opening (fresh wizard session)
          engaged: false,
        };
      });
    },
    
    closeWizard: (dismiss = false) => {
      set((state) => {
        const nextState: Partial<WizardUiState> = {
          open: false,
          // Reset manual flag when closing
          manual: false,
        };
        
        // If dismissed, mark as dismissed permanently
        if (dismiss) {
          nextState.dismissed = true;
        }
        
        return nextState;
      });
    },
    
    setEngaged: () => {
      set({ engaged: true });
    },
  };
});