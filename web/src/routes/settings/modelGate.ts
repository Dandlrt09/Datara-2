// Providers whose model ids are not filtered by the curated server whitelist.
// Mirrors server/api/routers/settings.py::_UNRESTRICTED_PROVIDERS (D6).
const UNRESTRICTED_PROVIDERS = new Set(["groq", "ollama", "lmstudio", "custom"]);

export function isModelRestricted(providerType: string | null | undefined): boolean {
  return !UNRESTRICTED_PROVIDERS.has(providerType ?? "");
}
