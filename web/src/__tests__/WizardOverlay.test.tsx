import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders } from './test-utils';

// Mock with vi.fn() directly
vi.mock('react-router-dom', async (importOriginal: () => Promise<typeof import('react-router-dom')>) => {
  const mod = await importOriginal();
  return {
    ...mod,
    useNavigate: () => vi.fn(),
  };
});

const { setEngagedMock } = vi.hoisted(() => ({ setEngagedMock: vi.fn() }));

vi.mock('../stores/useWizardStore', () => ({
  useWizardStore: (selector?: (s: Record<string, unknown>) => unknown) => {
    const state = {
      open: true,
      engaged: false,
      manual: false,
      dismissed: false,
      openWizard: vi.fn(),
      closeWizard: vi.fn(),
      setEngaged: setEngagedMock,
    };
    return selector ? selector(state) : state;
  },
}));

vi.mock('../lib/wizardStorage', () => ({
  writeWizardFlags: vi.fn(),
}));

vi.mock('../queries/useSessions', () => ({
  useCreateSession: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ id: 'ses-123' }),
    isPending: false,
  }),
}));

vi.mock('../queries/useFiles', () => ({
  useUploadFile: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  }),
}));

// Import after mocking
import { WizardOverlay } from '../components/WizardOverlay';

describe('WizardOverlay', () => {
  it('renders welcome step initially', () => {
    renderWithProviders(<WizardOverlay />);
    
    expect(screen.getByText('Welcome to Datara')).toBeTruthy();
    expect(screen.getByText('Get started')).toBeTruthy();
    expect(screen.getByText('Skip')).toBeTruthy();
  });

  it('shows progress indicator', () => {
    renderWithProviders(<WizardOverlay />);
    
    expect(screen.getByText('Step 1: Welcome')).toBeTruthy();
    expect(screen.getByText('Step 2: Upload')).toBeTruthy();
    expect(screen.getByText('Step 3: Question')).toBeTruthy();
    expect(screen.getByText('Step 4: Finish')).toBeTruthy();
  });

  it('advances to Upload on Get started (engagement + step)', () => {
    renderWithProviders(<WizardOverlay />);

    fireEvent.click(screen.getByText('Get started'));

    expect(screen.getByText('Upload your dataset')).toBeTruthy();
    expect(setEngagedMock).toHaveBeenCalled();
  });

  it('has dialog ARIA attributes', () => {
    renderWithProviders(<WizardOverlay />);
    
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-label')).toBe('First-run wizard');
  });
});