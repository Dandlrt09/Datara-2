export const SUGGESTIONS = [
  'What are the top 5 products by revenue?',
  'Show trends over time',
  'Summarize this dataset',
] as const;

export type Suggestion = typeof SUGGESTIONS[number];