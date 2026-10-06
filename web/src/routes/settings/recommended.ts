// Curated OpenRouter model catalog for non-technical data analysts (WU5).
//
// This is data, not logic: the recommended models, their prices, and the
// setup link are maintained here and consumed by both the Ajustes hub and
// the setup wizard. Prices are published USD per 1M tokens (D4 shape).
// Never fabricate entries — confirm model names and prices before changing.

export type RecommendedTier = "free" | "paid";

export interface RecommendedModel {
  model: string;
  label: string;
  tier: RecommendedTier;
  provider: "openrouter";
  recommended: boolean;
  setupUrl: string;
  guideId: string;
  inputUsdPerMillion: number;
  outputUsdPerMillion: number;
}

export const OPENROUTER_SETUP_URL = "https://openrouter.ai/keys";

export const RECOMMENDED_MODELS: RecommendedModel[] = [
  {
    model: "anthropic/claude-sonnet-5.5",
    label: "Claude Sonnet 5.5",
    tier: "paid",
    provider: "openrouter",
    recommended: true,
    setupUrl: OPENROUTER_SETUP_URL,
    guideId: "openrouter",
    inputUsdPerMillion: 2,
    outputUsdPerMillion: 10,
  },
  {
    model: "anthropic/claude-opus-5.5",
    label: "Claude Opus 5.5",
    tier: "paid",
    provider: "openrouter",
    recommended: false,
    setupUrl: OPENROUTER_SETUP_URL,
    guideId: "openrouter",
    inputUsdPerMillion: 4,
    outputUsdPerMillion: 20,
  },
  {
    model: "openai/gpt-6.1-sol",
    label: "GPT-6.1 Sol",
    tier: "paid",
    provider: "openrouter",
    recommended: false,
    setupUrl: OPENROUTER_SETUP_URL,
    guideId: "openrouter",
    inputUsdPerMillion: 2,
    outputUsdPerMillion: 10,
  },
  {
    model: "meta/muse-spark-1.3",
    label: "Muse Spark 1.3",
    tier: "paid",
    provider: "openrouter",
    recommended: false,
    setupUrl: OPENROUTER_SETUP_URL,
    guideId: "openrouter",
    inputUsdPerMillion: 1.25,
    outputUsdPerMillion: 4.25,
  },
  {
    model: "inclusionai/ling-3.1-flash",
    label: "Ling 3.1 Flash",
    tier: "free",
    provider: "openrouter",
    recommended: true,
    setupUrl: OPENROUTER_SETUP_URL,
    guideId: "openrouter",
    inputUsdPerMillion: 0,
    outputUsdPerMillion: 0,
  },
  {
    model: "thinkingmachines/inkling:free",
    label: "Inkling",
    tier: "free",
    provider: "openrouter",
    recommended: false,
    setupUrl: OPENROUTER_SETUP_URL,
    guideId: "openrouter",
    inputUsdPerMillion: 0,
    outputUsdPerMillion: 0,
  },
  {
    model: "nvidia/nemotron-3-ultra-550b-a55b:free",
    label: "Nemotron 3 Ultra",
    tier: "free",
    provider: "openrouter",
    recommended: false,
    setupUrl: OPENROUTER_SETUP_URL,
    guideId: "openrouter",
    inputUsdPerMillion: 0,
    outputUsdPerMillion: 0,
  },
  {
    model: "google/gemma-4-31b-it:free",
    label: "Gemma 4 31B",
    tier: "free",
    provider: "openrouter",
    recommended: false,
    setupUrl: OPENROUTER_SETUP_URL,
    guideId: "openrouter",
    inputUsdPerMillion: 0,
    outputUsdPerMillion: 0,
  },
];

/** Paid and free options, each already curated in recommended-first order. */
export const PAID_MODELS = RECOMMENDED_MODELS.filter((m) => m.tier === "paid");
export const FREE_MODELS = RECOMMENDED_MODELS.filter((m) => m.tier === "free");

/** Human price hint for an analyst: either a "Gratis" tag or both token rates. */
export function priceLabel(m: RecommendedModel): string {
  if (m.tier === "free") return "Gratis";
  return `Entrada $${m.inputUsdPerMillion.toFixed(2)} / Salida $${m.outputUsdPerMillion.toFixed(2)} por 1M tokens`;
}
