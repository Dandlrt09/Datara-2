import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useSettings, useUpdateSettings } from "../queries/useSettings";
import { QueryError } from "../components/ErrorCard";
import { PRESETS } from "./setup/presets";

type ProviderType = "openrouter" | "ollama" | "lmstudio" | "groq" | "custom";

interface SettingsForm {
  provider_type?: string;
  base_url?: string;
  api_key?: string;
  default_model?: string;
}

/** Extract a human-readable reason from an ApiError (FastAPI 422 detail). */
function saveErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "body" in error) {
    const detail = (error as { body?: { detail?: unknown } }).body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object") {
      return String((detail[0] as { msg?: unknown }).msg ?? "invalid value");
    }
  }
  return error instanceof Error ? error.message : "unknown error";
}

export default function SettingsView() {
  const { data: settings, isLoading, error, refetch } = useSettings();
  const updateSettings = useUpdateSettings();
  const { register, handleSubmit, reset, setValue, watch } = useForm<SettingsForm>();

  const [urlUnlocked, setUrlUnlocked] = useState(false);
  const providerType = watch("provider_type");
  const baseUrlValue = watch("base_url");
  const preset = PRESETS.find((p) => p.id === providerType);
  const presetDefault = preset?.defaultBaseUrl ?? "";
  const hasPresetDefault = presetDefault !== "";
  const urlEditable = !hasPresetDefault || urlUnlocked;
  const urlOverridden = hasPresetDefault && baseUrlValue !== presetDefault;

  // Sync form defaults once settings load. reset() MUST run inside an
  // effect: calling it during render updates form state while rendering,
  // which re-renders the form forever (blank screen). reset() does NOT
  // trigger the provider onChange, so a saved base_url is preserved.
  useEffect(() => {
    if (settings) {
      const loadedProvider = settings.provider_type ?? "";
      const loadedPreset = PRESETS.find((p) => p.id === loadedProvider);
      const savedUrl = settings.base_url ?? "";
      reset({
        provider_type: loadedProvider,
        // Preserve a saved URL (including a gateway override); fill the preset
        // default only when nothing was saved.
        base_url: savedUrl || loadedPreset?.defaultBaseUrl || "",
        api_key: "",
        default_model: settings.default_model ?? "",
      });
      setUrlUnlocked(false);
    }
  }, [settings, reset]);

  const onSubmit = (data: SettingsForm) => {
    updateSettings.mutate({
      provider_type: (data.provider_type || null) as ProviderType | null,
      base_url: data.base_url?.trim() ?? "",
      api_key: data.api_key?.trim() || undefined,
      default_model: data.default_model?.trim() || undefined,
    });
  };

  const toggleUrlEdit = () => setUrlUnlocked((v) => !v);
  const useDefault = () => setValue("base_url", presetDefault);

  if (isLoading) return <p>Loading settings...</p>;

  // Dropdown options: server whitelist, plus any legacy stored value that
  // predates the whitelist so the current selection is never lost.
  const modelOptions =
    settings?.default_model && !settings.allowed_models?.includes(settings.default_model)
      ? [settings.default_model, ...(settings.allowed_models ?? [])]
      : settings?.allowed_models ?? [];

  return (
    <div style={{ maxWidth: 500 }}>
      <h1>Settings</h1>
      <div style={{ marginBottom: 16 }}>
        <a href="/app/setup" style={{ display: "inline-block", padding: "8px 16px", backgroundColor: "#007acc", color: "white", borderRadius: 4, textDecoration: "none" }}>
          Configurar proveedor
        </a>
      </div>
      <QueryError error={error as Error | null} onRetry={refetch}>
        <form onSubmit={handleSubmit(onSubmit)}>
          <section style={{ marginBottom: 24 }}>
            <h2 style={{ fontSize: "1.1em", margin: "0 0 12px" }}>LLM Provider</h2>
            <div style={{ marginBottom: 16 }}>
              <label htmlFor="provider-type" style={{ display: "block", marginBottom: 4 }}>
                Provider
              </label>
              <select
                id="provider-type"
                {...register("provider_type", {
                  onChange: (event) => {
                    const nextPreset = PRESETS.find((p) => p.id === event.target.value);
                    setValue("base_url", nextPreset?.defaultBaseUrl ?? "");
                    setUrlUnlocked(false);
                  },
                })}
                style={{ width: "100%", padding: 8 }}
              >
                <option value="">—</option>
                {PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <label htmlFor="base-url" style={{ display: "block" }}>Base URL</label>
                {hasPresetDefault && (
                  <div style={{ display: "flex", gap: 12 }}>
                    {urlUnlocked && urlOverridden && (
                      <button
                        type="button"
                        onClick={useDefault}
                        style={{ background: "none", border: "none", color: "#007acc", cursor: "pointer", fontSize: "0.85em", padding: 0 }}
                      >
                        Use default
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={toggleUrlEdit}
                      style={{ background: "none", border: "none", color: "#007acc", cursor: "pointer", fontSize: "0.85em", padding: 0 }}
                    >
                      {urlUnlocked ? "Lock" : "Edit URL"}
                    </button>
                  </div>
                )}
              </div>
              <input
                id="base-url"
                {...register("base_url")}
                type="text"
                readOnly={!urlEditable}
                style={{ width: "100%", padding: 8, ...(urlEditable ? {} : { backgroundColor: "#f5f5f5", color: "#666" }) }}
              />
              {hasPresetDefault && !urlUnlocked && (
                <p style={{ fontSize: "0.85em", color: "#666", margin: "4px 0" }}>
                  {urlOverridden
                    ? "Custom URL (differs from the provider default)."
                    : "Provider default URL."}
                </p>
              )}
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", marginBottom: 4 }}>
                OpenAI API Key{" "}
                {settings?.has_api_key && (
                  <span style={{ color: "green", fontSize: "0.85em" }}>
                    (saved — leave blank to keep)
                  </span>
                )}
              </label>
              <input
                {...register("api_key")}
                type="password"
                placeholder="sk-..."
                style={{ width: "100%", padding: 8 }}
              />
              <p style={{ fontSize: "0.85em", color: "#666", margin: "4px 0" }}>
                Stored server-side and never sent back to the browser. Falls back
                to the OPENAI_API_KEY env var when empty.
              </p>
            </div>
          </section>
          <div style={{ marginBottom: 16 }}>
            <label htmlFor="default-model" style={{ display: "block", marginBottom: 4 }}>Default Model</label>
            <select id="default-model" {...register("default_model")} style={{ width: "100%", padding: 8 }}>
              <option value="">Server default (OPENAI_MODEL env)</option>
              {modelOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          {updateSettings.isSuccess && (
            <p style={{ color: "green" }}>Settings saved</p>
          )}
        {updateSettings.isError && (
          <p style={{ color: "red" }} role="alert">
            Failed to save settings: {saveErrorMessage(updateSettings.error)}
          </p>
        )}
          <button type="submit" disabled={updateSettings.isPending} style={{ padding: "8px 16px" }}>
            {updateSettings.isPending ? "Saving..." : "Save"}
          </button>
        </form>
      </QueryError>
    </div>
  );
}
