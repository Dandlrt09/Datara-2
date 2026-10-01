import type { ProfileSummary } from '../../queries/useFiles';

/** A suggested question shown in the wizard Question step. */
export type Suggestion = string;

/** Generic questions shown when no profile is available or it has no usable
 * columns. Kept free of dataset-specific nouns. */
export const FALLBACK_SUGGESTIONS: string[] = [
  'Summarize this dataset',
  'How many rows and columns does this dataset have?',
  'What columns does this dataset have?',
];

type ColumnKind = 'numeric' | 'datetime' | 'categorical' | 'other';

interface ProfileColumn {
  name: string;
  kind: ColumnKind;
  uniqueCount: number | null;
  hasMean: boolean;
}

const CATEGORICAL_DTYPES = new Set(['object', 'string', 'category', 'bool']);

function readStat(stats: Record<string, unknown>, column: string): Record<string, unknown> | null {
  const raw = stats?.[column];
  return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : null;
}

function readUniqueCount(stats: Record<string, unknown>, column: string): number | null {
  const value = readStat(stats, column)?.unique_count;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function readHasMean(stats: Record<string, unknown>, column: string): boolean {
  const value = readStat(stats, column)?.mean;
  return typeof value === 'number' && Number.isFinite(value);
}

function classify(dtype: string, uniqueCount: number | null): ColumnKind {
  const normalized = (dtype || '').toLowerCase();
  // Numeric wins first, but booleans are never numeric even though pandas dtype
  // names can nest them under integer-backed types.
  if ((normalized.includes('int') || normalized.includes('float')) && !normalized.includes('bool')) {
    return 'numeric';
  }
  if (normalized.includes('datetime') || normalized.includes('date')) {
    return 'datetime';
  }
  if (
    CATEGORICAL_DTYPES.has(normalized) &&
    uniqueCount !== null &&
    uniqueCount >= 2 &&
    uniqueCount <= 100
  ) {
    return 'categorical';
  }
  return 'other';
}

function toColumns(profile: ProfileSummary): ProfileColumn[] {
  const columns = profile?.schema?.columns ?? [];
  const stats = profile?.stats ?? {};
  return columns.map((column) => ({
    name: column.name,
    kind: classify(column.dtype, readUniqueCount(stats, column.name)),
    uniqueCount: readUniqueCount(stats, column.name),
    hasMean: readHasMean(stats, column.name),
  }));
}

/** First numeric column, preferring one that exposes a non-null mean. */
function pickNumeric(columns: ProfileColumn[]): ProfileColumn | null {
  const numeric = columns.filter((c) => c.kind === 'numeric');
  if (numeric.length === 0) return null;
  return numeric.find((c) => c.hasMean) ?? numeric[0];
}

/** First datetime column. */
function pickDatetime(columns: ProfileColumn[]): ProfileColumn | null {
  return columns.find((c) => c.kind === 'datetime') ?? null;
}

/** Categorical column with the lowest cardinality in [2, 100]. */
function pickCategorical(columns: ProfileColumn[]): ProfileColumn | null {
  const categorical = columns.filter((c) => c.kind === 'categorical');
  if (categorical.length === 0) return null;
  return categorical.reduce((best, current) =>
    (current.uniqueCount ?? Number.POSITIVE_INFINITY) < (best.uniqueCount ?? Number.POSITIVE_INFINITY)
      ? current
      : best,
  );
}

function pushUnique(target: string[], value: string): void {
  if (!target.includes(value)) target.push(value);
}

/**
 * Derive exactly three suggested questions from a dataset profile.
 *
 * Pure, synchronous and deterministic: the same profile always yields the same
 * three unique strings, in the same order. Falls back to generic copy when the
 * profile is null, empty, or has no usable columns. No LLM or network access.
 */
export function buildSuggestions(profile: ProfileSummary | null): string[] {
  if (!profile) return [...FALLBACK_SUGGESTIONS];

  const columns = toColumns(profile);
  const numeric = pickNumeric(columns);
  const datetime = pickDatetime(columns);
  const categorical = pickCategorical(columns);

  const candidates: string[] = [];
  // Priority ladder (D4): most specific pairing first, generic pad last.
  if (numeric && datetime) {
    candidates.push(`How has ${numeric.name} changed over ${datetime.name}?`);
  }
  if (numeric && categorical) {
    candidates.push(`What are the top ${categorical.name} by total ${numeric.name}?`);
  }
  if (numeric && numeric.hasMean) {
    candidates.push(`What is the average ${numeric.name}?`);
  }
  if (categorical) {
    candidates.push(`How many records are there per ${categorical.name}?`);
  }

  const result: string[] = [];
  for (const candidate of candidates) pushUnique(result, candidate);
  for (const fallback of FALLBACK_SUGGESTIONS) {
    if (result.length >= 3) break;
    pushUnique(result, fallback);
  }
  // Defensive guarantee: a column literally named after a fallback could
  // otherwise leave fewer than three. Deterministic and unique.
  for (let i = 0; result.length < 3; i += 1) {
    const fallback = FALLBACK_SUGGESTIONS[i % FALLBACK_SUGGESTIONS.length];
    pushUnique(result, `${fallback} (${result.length + 1})`);
  }
  return result.slice(0, 3);
}
