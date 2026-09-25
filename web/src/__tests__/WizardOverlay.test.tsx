import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, act, waitFor } from '@testing-library/react';
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

// Session-creation harness: lets a test defer session creation so it can leave
// the wizard while the request is still in flight. When `deferred` is null the
// mutation resolves immediately (default behaviour, keeps existing tests green).
const { createSessionHarness } = vi.hoisted(() => ({
  createSessionHarness: {
    deferred: null as null | {
      promise: Promise<{ id: string }>;
      resolve: (v: { id: string }) => void;
    },
  },
}));

vi.mock('../queries/useSessions', () => ({
  useCreateSession: () => ({
    mutateAsync: vi.fn(() =>
      createSessionHarness.deferred
        ? createSessionHarness.deferred.promise
        : Promise.resolve({ id: 'ses-123' })
    ),
    isPending: false,
  }),
}));

// Upload harness: the mocked mutation returns a promise we control, captures the
// AbortSignal handed to it, and flips isPending so the dropzone reflects a real
// in-flight upload. Assertions read the signal's `aborted` flag — the receipt the
// component can actually observe through the hook.
const uploadHarness = vi.hoisted(() => ({
  signals: [] as AbortSignal[],
  calls: 0,
}));

vi.mock('../queries/useFiles', async () => {
  const React = await import('react');
  return {
    useUploadFile: () => {
      const [isPending, setIsPending] = React.useState(false);
      const mutateAsync = React.useCallback((args: { signal?: AbortSignal }) => {
        if (args.signal) uploadHarness.signals.push(args.signal);
        uploadHarness.calls += 1;
        setIsPending(true);
        return new Promise<Record<string, never>>(() => {
          // Intentionally never settles: the test drives the abort.
        });
      }, []);
      return { mutateAsync, isPending, isError: false, error: null };
    },
    useSelectFileSheet: () => ({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
    }),
  };
});

// Import after mocking
import { WizardOverlay } from '../components/WizardOverlay';

function makeFile(name = 'data.csv') {
  return new File(['a,b\n1,2'], name, { type: 'text/csv' });
}

function getDropzone() {
  return screen
    .getByText(/Drag and drop a file here, or click to select|Uploading\.\.\./)
    .closest('div') as HTMLElement;
}

function fireDrop(dropzone: HTMLElement, file = makeFile()) {
  fireEvent.drop(dropzone, { dataTransfer: { files: [file], types: ['Files'] } });
}

async function goToUploadWithPendingUpload() {
  const rendered = renderWithProviders(<WizardOverlay />);
  fireEvent.click(screen.getByText('Get started'));
  const dropzone = getDropzone();
  await act(async () => {
    fireDrop(dropzone);
  });
  await waitFor(() => expect(uploadHarness.calls).toBe(1));
  await waitFor(() => expect(screen.getByText('Uploading...')).toBeTruthy());
  expect(uploadHarness.signals[0].aborted).toBe(false);
  return { ...rendered, dropzone };
}

beforeEach(() => {
  uploadHarness.signals.length = 0;
  uploadHarness.calls = 0;
  createSessionHarness.deferred = null;
});

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

  it('aborts an in-flight upload when Skip is pressed', async () => {
    await goToUploadWithPendingUpload();

    fireEvent.click(screen.getByText('Skip'));

    expect(uploadHarness.signals[0].aborted).toBe(true);
  });

  it('aborts an in-flight upload when Escape is pressed', async () => {
    await goToUploadWithPendingUpload();

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });

    expect(uploadHarness.signals[0].aborted).toBe(true);
  });

  it('aborts an in-flight upload when the wizard unmounts', async () => {
    const { unmount } = await goToUploadWithPendingUpload();

    unmount();

    expect(uploadHarness.signals[0].aborted).toBe(true);
  });

  it('ignores a second drop while an upload is pending', async () => {
    const { dropzone } = await goToUploadWithPendingUpload();

    fireDrop(dropzone, makeFile('second.csv'));

    await waitFor(() => expect(uploadHarness.calls).toBe(1));
    expect(uploadHarness.signals.length).toBe(1);
  });

  it('still aborts an in-flight upload from the in-step Cancel button', async () => {
    await goToUploadWithPendingUpload();

    fireEvent.click(screen.getByText('Cancel'));

    expect(uploadHarness.signals[0].aborted).toBe(true);
  });

  it('does not start the upload when the wizard is left during session creation', async () => {
    const rendered = renderWithProviders(<WizardOverlay />);
    fireEvent.click(screen.getByText('Get started'));

    // Defer session creation so the wizard can be left while it is in flight.
    let resolveSession!: (v: { id: string }) => void;
    createSessionHarness.deferred = {
      promise: new Promise<{ id: string }>((resolve) => {
        resolveSession = resolve;
      }),
      resolve: (v) => resolveSession(v),
    };

    const dropzone = getDropzone();
    await act(async () => {
      fireDrop(dropzone);
    });

    // Leave the wizard while session creation is still pending.
    fireEvent.click(screen.getByText('Skip'));

    // Session creation now resolves late; the upload must NOT start.
    await act(async () => {
      createSessionHarness.deferred!.resolve({ id: 'ses-late' });
      await Promise.resolve();
    });

    expect(uploadHarness.calls).toBe(0);
    rendered.unmount();
  });

  it('renders an upload input whose accept list excludes .tab (F6)', () => {
    const { container } = renderWithProviders(<WizardOverlay />);
    fireEvent.click(screen.getByText('Get started'));

    const input = container.querySelector('input[type="file"]') as HTMLInputElement | null;

    expect(input).toBeTruthy();
    const accept = input?.getAttribute('accept') ?? '';
    expect(accept).not.toContain('.tab');
    expect(accept).toContain('.tsv');
  });
});
