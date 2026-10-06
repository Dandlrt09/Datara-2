// Curated model catalog per provider for non-technical data analysts (WU5).
//
// This is data, not logic: the recommended models, their prices, and the
// setup link are maintained here and consumed by both the Ajustes hub and
// the setup wizard. Prices are published USD per 1M tokens (D4 shape).
// Never fabricate entries — confirm model names and prices before changing.
//
// The UI only shows the catalog for the currently selected provider; there is
// no cross-provider list. Providers without a curated catalog (Ollama, LM
// Studio, Custom) render no recommended section.

export type RecommendedTier = "free" | "paid";
export type RecommendedProvider = "openrouter" | "groq";

export interface RecommendedModel {
  model: string;
  label: string;
  tier: RecommendedTier;
  provider: RecommendedProvider;
  recommended: boolean;
  setupUrl: string;
  guideId: string;
  inputUsdPerMillion: number;
  outputUsdPerMillion: number;
}

export const OPENROUTER_SETUP_URL = "https://openrouter.ai/keys";
export const GROQ_SETUP_URL = "https://console.groq.com/keys";

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
  // Groq curated catalog (public docs console.groq.com/docs/models, 2026-10-06).
  // Groq is unrestricted (no whitelist); only pricing is curated here.
  // `llama-3.3-70b-versatile` / `llama-3.1-8b-instant` are excluded: no
  // published price (Enterprise) → NULL cost. Groq has no free tier.
  {
    model: "openai/gpt-oss-120b",
    label: "GPT-OSS 120B",
    tier: "paid",
    provider: "groq",
    recommended: true,
    setupUrl: GROQ_SETUP_URL,
    guideId: "groq",
    inputUsdPerMillion: 0.15,
    outputUsdPerMillion: 0.6,
  },
  {
    model: "openai/gpt-oss-20b",
    label: "GPT-OSS 20B",
    tier: "paid",
    provider: "groq",
    recommended: false,
    setupUrl: GROQ_SETUP_URL,
    guideId: "groq",
    inputUsdPerMillion: 0.075,
    outputUsdPerMillion: 0.3,
  },
  {
    model: "qwen/qwen3.8-27b",
    label: "Qwen 3.8 27B (preview)",
    tier: "paid",
    provider: "groq",
    recommended: false,
    setupUrl: GROQ_SETUP_URL,
    guideId: "groq",
    inputUsdPerMillion: 0.8,
    outputUsdPerMillion: 4.0,
  },
];

/** The curated models for one provider (empty when it has no catalog). */
export function modelsForProvider(
  provider: string | null | undefined,
): RecommendedModel[] {
  return RECOMMENDED_MODELS.filter((m) => m.provider === provider);
}

/** The provider's curated catalog split by tier, each already in order. */
export function catalogFor(provider: string | null | undefined): {
  paid: RecommendedModel[];
  free: RecommendedModel[];
} {
  const models = modelsForProvider(provider);
  return {
    paid: models.filter((m) => m.tier === "paid"),
    free: models.filter((m) => m.tier === "free"),
  };
}

/** Human price hint for an analyst: either a "Gratis" tag or both token rates. */
export function priceLabel(m: RecommendedModel): string {
  if (m.tier === "free") return "Gratis";
  return `Entrada $${m.inputUsdPerMillion.toFixed(2)} / Salida $${m.outputUsdPerMillion.toFixed(2)} por 1M tokens`;
}
