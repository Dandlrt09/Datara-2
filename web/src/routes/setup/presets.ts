// Provider presets for the setup wizard.

export interface ProviderPreset {
  id: string;
  label: string;
  defaultBaseUrl: string;
  apiKeyRequired: boolean;
}

export const PRESETS: ProviderPreset[] = [
  {
    id: "openrouter",
    label: "OpenRouter",
    defaultBaseUrl: "https://openrouter.ai/api/v1",
    apiKeyRequired: true,
  },
  {
    id: "ollama",
    label: "Ollama",
    defaultBaseUrl: "http://localhost:11434/v1",
    apiKeyRequired: false,
  },
  {
    id: "lmstudio",
    label: "LM Studio",
    defaultBaseUrl: "http://localhost:1234/v1",
    apiKeyRequired: false,
  },
  {
    id: "groq",
    label: "Groq",
    defaultBaseUrl: "https://api.groq.com/openai/v1",
    apiKeyRequired: true,
  },
  {
    id: "custom",
    label: "Custom",
    defaultBaseUrl: "",
    apiKeyRequired: true,
  },
];