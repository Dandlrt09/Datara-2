import { describe, it, expect } from 'vitest';
import {
  buildSuggestions,
  FALLBACK_SUGGESTIONS,
} from '../components/WizardOverlay/suggestions';
import type { ProfileSummary } from '../queries/useFiles';

interface ColumnSpec {
  name: string;
  dtype: string;
  uniqueCount?: number;
  mean?: number;
}

function makeProfile(columns: ColumnSpec[], fileId = 1): ProfileSummary {
  const stats: Record<string, unknown> = {};
  for (const column of columns) {
    const entry: Record<string, unknown> = {};
    if (column.uniqueCount !== undefined) entry.unique_count = column.uniqueCount;
    if (column.mean !== undefined) entry.mean = column.mean;
    stats[column.name] = entry;
  }
  return {
    file_id: fileId,
    schema: { columns: columns.map(({ name, dtype }) => ({ name, dtype })) },
    stats,
    sample: [],
  };
}

describe('buildSuggestions', () => {
  it('returns the generic fallbacks when the profile is null', () => {
    expect(buildSuggestions(null)).toEqual(FALLBACK_SUGGESTIONS);
  });

  it('returns the generic fallbacks when the profile has no columns', () => {
    expect(buildSuggestions(makeProfile([]))).toEqual(FALLBACK_SUGGESTIONS);
  });

  it('returns the generic fallbacks when no column has a usable dtype', () => {
    const profile = makeProfile([{ name: 'notes', dtype: 'geography' }]);
    expect(buildSuggestions(profile)).toEqual(FALLBACK_SUGGESTIONS);
  });

  it('derives a time-series question from numeric + datetime columns', () => {
    const profile = makeProfile([
      { name: 'temperature', dtype: 'float64', mean: 18.5 },
      { name: 'observed_at', dtype: 'datetime64[ns]' },
    ]);

    const suggestions = buildSuggestions(profile);

    expect(suggestions).toHaveLength(3);
    expect(suggestions[0]).toBe('How has temperature changed over observed_at?');
    expect(suggestions).toContain('What is the average temperature?');
  });

  it('derives the full ladder from numeric + categorical + datetime columns', () => {
    const profile = makeProfile([
      { name: 'revenue', dtype: 'float64', mean: 1200.5 },
      { name: 'product', dtype: 'object', uniqueCount: 5 },
      { name: 'sold_at', dtype: 'date' },
    ]);

    const suggestions = buildSuggestions(profile);

    expect(suggestions).toEqual([
      'How has revenue changed over sold_at?',
      'What are the top product by total revenue?',
      'What is the average revenue?',
    ]);
  });

  it('derives a grouping question from a numeric + categorical pair', () => {
    const profile = makeProfile([
      { name: 'revenue', dtype: 'float64', mean: 10 },
      { name: 'product', dtype: 'object', uniqueCount: 5 },
    ]);

    const suggestions = buildSuggestions(profile);

    expect(suggestions[0]).toBe('What are the top product by total revenue?');
    expect(suggestions).toContain('What is the average revenue?');
  });

  it('derives an average question from a numeric column with a mean', () => {
    const profile = makeProfile([{ name: 'score', dtype: 'int64', mean: 7 }]);

    const suggestions = buildSuggestions(profile);

    expect(suggestions[0]).toBe('What is the average score?');
    expect(suggestions).toHaveLength(3);
    expect(new Set(suggestions).size).toBe(3);
  });

  it('falls back when a numeric column has no mean and nothing else is usable', () => {
    const profile = makeProfile([{ name: 'score', dtype: 'int64' }]);
    expect(buildSuggestions(profile)).toEqual(FALLBACK_SUGGESTIONS);
  });

  it('derives a per-group count from a single categorical column', () => {
    const profile = makeProfile([{ name: 'city', dtype: 'category', uniqueCount: 8 }]);

    const suggestions = buildSuggestions(profile);

    expect(suggestions[0]).toBe('How many records are there per city?');
    expect(suggestions).toHaveLength(3);
    expect(new Set(suggestions).size).toBe(3);
  });

  it('ignores high-cardinality object columns (not plausible grouping keys)', () => {
    const profile = makeProfile([{ name: 'id', dtype: 'object', uniqueCount: 5000 }]);
    expect(buildSuggestions(profile)).toEqual(FALLBACK_SUGGESTIONS);
  });

  it('treats booleans as categorical, never numeric', () => {
    const profile = makeProfile([{ name: 'is_active', dtype: 'bool', uniqueCount: 2 }]);

    const suggestions = buildSuggestions(profile);

    expect(suggestions[0]).toBe('How many records are there per is_active?');
  });

  it('prefers the numeric column that exposes a mean', () => {
    const profile = makeProfile([
      { name: 'count', dtype: 'int64' },
      { name: 'amount', dtype: 'float64', mean: 4.2 },
    ]);

    expect(buildSuggestions(profile)[0]).toBe('What is the average amount?');
  });

  it('picks the lowest-cardinality categorical column', () => {
    const profile = makeProfile([
      { name: 'region', dtype: 'object', uniqueCount: 40 },
      { name: 'segment', dtype: 'string', uniqueCount: 3 },
    ]);

    expect(buildSuggestions(profile)[0]).toBe('How many records are there per segment?');
  });

  it('always returns exactly three unique strings across varied profiles', () => {
    const profiles: Array<ProfileSummary> = [
      makeProfile([]),
      makeProfile([{ name: 'a', dtype: 'object', uniqueCount: 2 }]),
      makeProfile([{ name: 'a', dtype: 'float64', mean: 1 }]),
      makeProfile([
        { name: 'a', dtype: 'float64', mean: 1 },
        { name: 'b', dtype: 'object', uniqueCount: 4 },
        { name: 'c', dtype: 'datetime64[ns]' },
      ]),
    ];

    for (const profile of profiles) {
      const suggestions = buildSuggestions(profile);
      expect(suggestions).toHaveLength(3);
      expect(new Set(suggestions).size).toBe(3);
      for (const suggestion of suggestions) {
        expect(typeof suggestion).toBe('string');
        expect(suggestion.length).toBeGreaterThan(0);
      }
    }
  });

  it('is deterministic: the same profile yields the same questions in order', () => {
    const profile = makeProfile([
      { name: 'revenue', dtype: 'float64', mean: 1200 },
      { name: 'product', dtype: 'object', uniqueCount: 5 },
      { name: 'sold_at', dtype: 'date' },
    ]);

    expect(buildSuggestions(profile)).toEqual(buildSuggestions(profile));
  });
});
