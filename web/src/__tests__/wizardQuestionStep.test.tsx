import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders } from './test-utils';

// The component fetches the profile through useProfile; the harness lets each
// test decide what the hook returns without touching react-query or the network.
// `calls` records every fileId handed to the hook so tests can prove the id is
// propagated rather than silently dropped to null.
const profileHarness = vi.hoisted(() => ({
  current: undefined as unknown,
  calls: [] as Array<number | null>,
}));

vi.mock('../queries/useFiles', () => ({
  useProfile: (fileId: number | null) => {
    profileHarness.calls.push(fileId);
    return profileHarness.current;
  },
}));

import { QuestionStep } from '../components/WizardOverlay/QuestionStep';

const revenueProductProfile = {
  file_id: 1,
  schema: {
    columns: [
      { name: 'revenue', dtype: 'float64' },
      { name: 'product', dtype: 'object' },
    ],
  },
  stats: {
    revenue: { mean: 1200.5, unique_count: 900 },
    product: { unique_count: 5 },
  },
  sample: [],
};

function renderStep(onNext = vi.fn(), onSkip = vi.fn()) {
  return renderWithProviders(
    <QuestionStep fileId={1} onSkip={onSkip} onNext={onNext} />,
  );
}

describe('QuestionStep', () => {
  beforeEach(() => {
    profileHarness.current = { data: null, isLoading: false, isError: false };
    profileHarness.calls.length = 0;
  });

  it('requests the profile for exactly the fileId it was given', () => {
    renderWithProviders(
      <QuestionStep fileId={7} onSkip={vi.fn()} onNext={vi.fn()} />,
    );

    // Discriminating assertion: the fileId must reach useProfile unchanged.
    // Passing null (or any other id) would fail this — a null id disables the
    // query in production, so the profile would never load.
    expect(profileHarness.calls).toEqual([7]);
    expect(profileHarness.calls).not.toContain(null);
  });

  it('renders profile-derived questions that name the dataset columns', () => {
    profileHarness.current = {
      data: revenueProductProfile,
      isLoading: false,
      isError: false,
    };

    renderStep();

    expect(screen.getByText('What are the top product by total revenue?')).toBeTruthy();
    expect(screen.getByText('What is the average revenue?')).toBeTruthy();
    expect(screen.getByText('How many records are there per product?')).toBeTruthy();
  });

  it('passes the selected question to onNext when confirmed', () => {
    profileHarness.current = {
      data: revenueProductProfile,
      isLoading: false,
      isError: false,
    };
    const onNext = vi.fn();

    renderStep(onNext);

    fireEvent.click(screen.getByText('What is the average revenue?'));
    fireEvent.click(screen.getByText('Next'));

    expect(onNext).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledWith('What is the average revenue?');
  });

  it('does not call onNext until a question is selected', () => {
    profileHarness.current = {
      data: revenueProductProfile,
      isLoading: false,
      isError: false,
    };
    const onNext = vi.fn();

    renderStep(onNext);

    fireEvent.click(screen.getByText('Next'));

    expect(onNext).not.toHaveBeenCalled();
  });

  it('renders the generic fallbacks when no profile data is available', () => {
    renderStep();

    expect(screen.getByText('Summarize this dataset')).toBeTruthy();
    expect(
      screen.getByText('How many rows and columns does this dataset have?'),
    ).toBeTruthy();
    expect(screen.getByText('What columns does this dataset have?')).toBeTruthy();
  });
});
