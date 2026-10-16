// Providers whose model ids are not filtered by the curated server whitelist.
//
// SOURCE OF TRUTH: server/api/routers/settings.py::_UNRESTRICTED_PROVIDERS (D6).
// That frozenset is the real gate (applied at chat time); this Set is a UI
// mirror so the wizard and the settings hub render the same model list the
// server will accept. Editing one side alone silently re-introduces the D6
// dead-end, so the two lists are kept equal by
// tests/unit/architecture/test_model_gate_parity.py — it reads this
// declaration and fails the build when they drift.
export const UNRESTRICTED_PROVIDERS = new Set(["groq", "ollama", "lmstudio", "custom"]);

export function isModelRestricted(providerType: string | null | undefined): boolean {
  return !UNRESTRICTED_PROVIDERS.has(providerType ?? "");
}
