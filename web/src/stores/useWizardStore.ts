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
    
    openWizard: (_manual = false) => {
      set((state) => {
        // Manual reopens bypass the dismissed latch: the spec requires
        // reopen-after-skip regardless of persisted flags. Auto-opens stay
        // latched so the wizard never reappears after skip/finish.
        //
        // Nothing opens this store on its own any more (F4/S5): the auto-open on
        // /app and the button in the empty chat state are gone, and the guided
        // tour took both entry points. This manual path is kept intact so the
        // wizard can be restored with one line.
        if (state.dismissed && !_manual) {
          return state;
        }
        
        return {
          open: true,
          manual: _manual,
          // Reset engaged when opening (fresh wizard session)
          engaged: false,
        };
      });
    },
    
    closeWizard: (dismiss = false) => {
      set(() => {
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