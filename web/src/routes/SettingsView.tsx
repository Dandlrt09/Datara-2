import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useSettings, useUpdateSettings, type UserSettings } from "../queries/useSettings";
import { QueryError } from "../components/ErrorCard";
import { PRESETS } from "./setup/presets";
import { useFetchModels } from "./setup/useFetchModels";
import ProviderGuide from "./settings/ProviderGuide";
import {
  FREE_MODELS,
  OPENROUTER_SETUP_URL,
  PAID_MODELS,
  priceLabel,
  type RecommendedModel,
} from "./settings/recommended";

type ProviderType = "openrouter" | "ollama" | "lmstudio" | "groq" | "custom";

/**
 * Honest save lifecycle. A successful PUT is not enough to claim success:
 * when a provider is configured we probe it before reporting "Connected".
 */
type SaveStatus =
  | "idle"
  | "saving"
  | "checking"
  | "saved"
  | "connected"
  | "saved-unverified"
  | "save-error";

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

/** One tier group of the curated catalog (paid or free). */
function RecommendedList({
  models,
  tierLabel,
}: {
  models: RecommendedModel[];
  tierLabel: string;
}) {
  return (
    <>
      {models.map((m) => (
        <div
          key={m.model}
          style={{ border: "1px solid #ddd", borderRadius: 4, padding: 12, marginBottom: 8 }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>
              <strong>{m.label}</strong>
              {m.recommended && (
                <span style={{ marginLeft: 8, color: "#007acc", fontSize: "0.8em" }}>
                  (Recomendado)
                </span>
              )}
            </span>
            <span style={{ fontSize: "0.8em", color: "#666" }}>{tierLabel}</span>
          </div>
          <p style={{ margin: "4px 0 0", fontSize: "0.85em", color: "#666" }}>{priceLabel(m)}</p>
        </div>
      ))}
    </>
  );
}

export default function SettingsView() {
  const { data: settings, isLoading, error, refetch } = useSettings();
  const updateSettings = useUpdateSettings();
  const { fetchModels } = useFetchModels();
  const { register, handleSubmit, reset, setValue, watch } = useForm<SettingsForm>();

  const [urlUnlocked, setUrlUnlocked] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [statusDetail, setStatusDetail] = useState<string | null>(null);
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

  const onSubmit = async (data: SettingsForm) => {
    setSaveStatus("saving");
    setStatusDetail(null);

    // 1. Persist first. A failed save is a hard error and must not probe.
    let saved: UserSettings;
    try {
      saved = await updateSettings.mutateAsync({
        provider_type: (data.provider_type || null) as ProviderType | null,
        base_url: data.base_url?.trim() ?? "",
        api_key: data.api_key?.trim() || undefined,
        default_model: data.default_model?.trim() || undefined,
      });
    } catch (err) {
      setSaveStatus("save-error");
      setStatusDetail(saveErrorMessage(err));
      return;
    }

    // 2. Trust the server-returned provider_type; fall back to the submitted
    // value when the response omits it. A falsy value means the provider was
    // cleared: there is nothing to verify, so a plain success is honest.
    const effectiveProvider = saved?.provider_type ?? data.provider_type ?? null;
    if (!effectiveProvider) {
      setSaveStatus("saved");
      return;
    }

    // 3. Probe the persisted config. A failed probe does not roll back the
    // save; it reports the truth.
    setSaveStatus("checking");
    try {
      const res = await fetchModels();
      if (res.error == null) {
        setSaveStatus("connected");
      } else {
        setSaveStatus("saved-unverified");
        setStatusDetail(res.error.message);
      }
    } catch (err) {
      setSaveStatus("saved-unverified");
      setStatusDetail(err instanceof Error ? err.message : "unknown error");
    }
  };

  const toggleUrlEdit = () => setUrlUnlocked((v) => !v);
  const useDefault = () => setValue("base_url", presetDefault);

  if (isLoading) return <p>Cargando ajustes...</p>;

  // Dropdown options: server whitelist, plus any legacy stored value that
  // predates the whitelist so the current selection is never lost.
  const modelOptions =
    settings?.default_model && !settings.allowed_models?.includes(settings.default_model)
      ? [settings.default_model, ...(settings.allowed_models ?? [])]
      : settings?.allowed_models ?? [];

  return (
    <div style={{ maxWidth: 500 }}>
      <h1>Ajustes</h1>
      <div style={{ marginBottom: 16 }}>
        <a href="/app/setup" style={{ display: "inline-block", padding: "8px 16px", backgroundColor: "#007acc", color: "white", borderRadius: 4, textDecoration: "none" }}>
          Configurar proveedor
        </a>
      </div>
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: "1.1em", margin: "0 0 12px" }}>Modelos recomendados</h2>
        <p style={{ fontSize: "0.9em", color: "#666", marginTop: 0 }}>
          Opciones pensadas para análisis de datos. Puedes usar un modelo gratuito o
          cargar créditos para los de pago.
        </p>
        <h3 style={{ fontSize: "0.95em", margin: "0 0 8px" }}>De pago</h3>
        <RecommendedList models={PAID_MODELS} tierLabel="De pago" />
        <h3 style={{ fontSize: "0.95em", margin: "0 0 8px" }}>Gratis</h3>
        <RecommendedList models={FREE_MODELS} tierLabel="Gratis" />
        <a
          href={OPENROUTER_SETUP_URL}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: "0.9em" }}
        >
          Obtener una clave de API en OpenRouter
        </a>
      </section>
      <ProviderGuide guideId="openrouter" />
      <QueryError error={error as Error | null} onRetry={refetch}>
        <form onSubmit={handleSubmit(onSubmit)}>
          <section style={{ marginBottom: 24 }}>
            <h2 style={{ fontSize: "1.1em", margin: "0 0 12px" }}>Proveedor de LLM</h2>
            <div style={{ marginBottom: 16 }}>
              <label htmlFor="provider-type" style={{ display: "block", marginBottom: 4 }}>
                Proveedor
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
                <label htmlFor="base-url" style={{ display: "block" }}>URL base</label>
                {hasPresetDefault && (
                  <div style={{ display: "flex", gap: 12 }}>
                    {urlUnlocked && urlOverridden && (
                      <button
                        type="button"
                        onClick={useDefault}
                        style={{ background: "none", border: "none", color: "#007acc", cursor: "pointer", fontSize: "0.85em", padding: 0 }}
                      >
                        Usar predeterminada
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={toggleUrlEdit}
                      style={{ background: "none", border: "none", color: "#007acc", cursor: "pointer", fontSize: "0.85em", padding: 0 }}
                    >
                      {urlUnlocked ? "Bloquear" : "Editar URL"}
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
                    ? "URL personalizada (distinta de la predeterminada del proveedor)."
                    : "URL predeterminada del proveedor."}
                </p>
              )}
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", marginBottom: 4 }}>
                Clave de API de OpenAI{" "}
                {settings?.has_api_key && (
                  <span style={{ color: "green", fontSize: "0.85em" }}>
                    (guardada — deja en blanco para mantenerla)
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
                Se guarda en el servidor y nunca se devuelve al navegador. Si se
                deja vacía, se usa la variable de entorno OPENAI_API_KEY.
              </p>
            </div>
          </section>
          <div style={{ marginBottom: 16 }}>
            <label htmlFor="default-model" style={{ display: "block", marginBottom: 4 }}>Modelo predeterminado</label>
            <select id="default-model" {...register("default_model")} style={{ width: "100%", padding: 8 }}>
              <option value="">Predeterminado del servidor (variable OPENAI_MODEL)</option>
              {modelOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          {saveStatus === "saved" && (
            <p style={{ color: "green" }}>Ajustes guardados</p>
          )}
          {saveStatus === "connected" && (
            <p style={{ color: "green" }}>Guardado · Conectado</p>
          )}
          {saveStatus === "saved-unverified" && (
            <p style={{ color: "red" }} role="alert">
              Guardado, pero falló la conexión: {statusDetail}
            </p>
          )}
          {saveStatus === "save-error" && (
            <p style={{ color: "red" }} role="alert">
              No se pudieron guardar los ajustes: {statusDetail}
            </p>
          )}
          <button
            type="submit"
            disabled={saveStatus === "saving" || saveStatus === "checking"}
            style={{ padding: "8px 16px" }}
          >
            {saveStatus === "saving" ? "Guardando..." : saveStatus === "checking" ? "Comprobando..." : "Guardar"}
          </button>
        </form>
      </QueryError>
    </div>
  );
}
