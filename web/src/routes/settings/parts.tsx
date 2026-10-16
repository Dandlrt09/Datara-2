// Presentational pieces shared by every provider-configuration variant.
//
// The variants under experiment (one screen with two modes, one linear view,
// two screens) differ only in how they group and sequence these pieces; the
// rules behind them live in `useProviderSetup.ts`. Keeping the field rendering
// here is what stops the fusion from growing a second provider form the day
// someone adds a variant — which is exactly the duplication this feature is
// undoing (the wizard and the hub each had their own).
//
// Two decisions are encoded here because both screens used to disagree:
//   - the model list for a restricted provider comes from the server whitelist
//     (it arrives with the settings and cannot fail), not from a live fetch;
//     the live list is only *needed* for providers that own their catalog.
//   - an API key is only marked as required when the server holds none.

import type { CSSProperties } from "react";
import { COPY } from "../setup/copy";
import { priceLabel } from "./recommended";
import type { ProviderSetup } from "./useProviderSetup";

/** A link-styled inline button, shared so the two screens look alike. */
const LINK_BUTTON: CSSProperties = {
  background: "none",
  border: "none",
  color: "#007acc",
  cursor: "pointer",
  fontSize: "0.85em",
  padding: 0,
};

const FIELD_LABEL: CSSProperties = { display: "block", marginBottom: 4 };
const INPUT: CSSProperties = { width: "100%", padding: 8 };
const HINT: CSSProperties = { fontSize: "0.85em", color: "#666", margin: "4px 0" };

interface PartProps {
  setup: ProviderSetup;
}

/** Dropdown form of the provider choice (the hub and the advanced mode). */
export function ProviderSelect({ setup, id = "provider-type" }: PartProps & { id?: string }) {
  const { form, providerOptions, preset, chooseProvider } = setup;
  return (
    <div style={{ marginBottom: 16 }}>
      <label htmlFor={id} style={FIELD_LABEL}>
        Proveedor
      </label>
      <select
        id={id}
        {...form.register("provider_type", {
          onChange: (event) => chooseProvider(event.target.value),
        })}
        style={INPUT}
      >
        <option value="">—</option>
        {providerOptions.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
      {preset?.legacy && <p style={HINT}>{COPY.LEGACY_PROVIDER_HINT}</p>}
    </div>
  );
}

/**
 * Radio form of the same choice: the guided flow makes the first decision
 * visible instead of hiding it behind a dropdown, and names which providers
 * ask for a key before the user is asked for one.
 */
export function ProviderChoices({ setup }: PartProps) {
  const { form, providerOptions, preset, chooseProvider } = setup;
  return (
    <div style={{ marginBottom: 16 }}>
      {providerOptions.map((option) => (
        <div key={option.id} style={{ marginBottom: 8 }}>
          <label>
            <input
              type="radio"
              value={option.id}
              {...form.register("provider_type", {
                onChange: (event) => chooseProvider(event.target.value),
              })}
            />{" "}
            {option.label}
            {option.apiKeyRequired && " (clave de API requerida)"}
          </label>
          {preset?.id === option.id && option.defaultBaseUrl && (
            <div style={{ ...HINT, marginLeft: 24 }}>
              URL predeterminada: {option.defaultBaseUrl}
            </div>
          )}
        </div>
      ))}
      {preset?.legacy && <p style={HINT}>{COPY.LEGACY_PROVIDER_HINT}</p>}
    </div>
  );
}

/**
 * Base URL. A preset URL is read-only until the user asks to edit it, and an
 * override can be reverted to the preset default: the field never hides which
 * endpoint Datara will actually call.
 */
export function BaseUrlField({ setup, id = "base-url" }: PartProps & { id?: string }) {
  const {
    form,
    values,
    presetDefault,
    hasPresetDefault,
    urlUnlocked,
    unlockUrl,
    lockUrl,
    restorePresetDefaultUrl,
  } = setup;
  const editable = !hasPresetDefault || urlUnlocked;
  const overridden = hasPresetDefault && values.base_url !== presetDefault;

  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 4,
        }}
      >
        <label htmlFor={id} style={{ display: "block" }}>
          URL base
        </label>
        {hasPresetDefault && (
          <div style={{ display: "flex", gap: 12 }}>
            {urlUnlocked && overridden && (
              <button type="button" onClick={restorePresetDefaultUrl} style={LINK_BUTTON}>
                Usar predeterminada
              </button>
            )}
            <button type="button" onClick={urlUnlocked ? lockUrl : unlockUrl} style={LINK_BUTTON}>
              {urlUnlocked ? "Bloquear" : "Editar URL"}
            </button>
          </div>
        )}
      </div>
      <input
        id={id}
        type="text"
        {...form.register("base_url")}
        readOnly={!editable}
        style={{ ...INPUT, ...(editable ? {} : { backgroundColor: "#f5f5f5", color: "#666" }) }}
      />
      {hasPresetDefault && !urlUnlocked && (
        <p style={HINT}>
          {overridden
            ? "URL personalizada (distinta de la predeterminada del proveedor)."
            : "URL predeterminada del proveedor."}
        </p>
      )}
    </div>
  );
}

/** Keyless providers (Ollama, LM Studio) need the endpoint, not a key. */
export function KeylessProviderNote({ setup }: PartProps) {
  const { values, preset } = setup;
  if (!preset || preset.apiKeyRequired) return null;
  return (
    <div style={{ marginBottom: 16, padding: 12, backgroundColor: "#f0f0f0", borderRadius: 4 }}>
      <p style={{ margin: "0 0 8px" }}>{COPY.KEYLESS_NO_KEY_REQUIRED(preset.label)}</p>
      <p style={{ margin: "0 0 4px" }}>
        {COPY.KEYLESS_ENDPOINT_LABEL}{" "}
        <code>{values.base_url || preset.defaultBaseUrl}</code>
      </p>
      <p style={{ margin: 0, ...HINT }}>{COPY.KEYLESS_SERVER_HINT(preset.label)}</p>
    </div>
  );
}

/**
 * API key. The stored key never comes back from the server, so an empty field
 * means "keep the stored one" — and only then is it not required.
 */
export function ApiKeyField({ setup, id = "api-key" }: PartProps & { id?: string }) {
  const { form, preset, settings } = setup;
  if (!preset?.apiKeyRequired) return null;
  const stored = settings?.has_api_key === true;

  return (
    <div style={{ marginBottom: 16 }}>
      <label htmlFor={id} style={FIELD_LABEL}>
        Clave de API {!stored && "*"}{" "}
        {stored && (
          <span style={{ color: "green", fontSize: "0.85em" }}>
            (guardada — deja en blanco para mantenerla)
          </span>
        )}
      </label>
      <input
        id={id}
        type="password"
        placeholder="sk-..."
        {...form.register("api_key")}
        style={INPUT}
      />
      <p style={HINT}>
        Se guarda en el servidor y nunca se devuelve al navegador. Si se deja vacía, se
        usa la variable de entorno OPENAI_API_KEY.
      </p>
    </div>
  );
}

/**
 * The curated catalog for the selected provider, as clickable cards: the label
 * the analyst understands, the price, and the tier. It doubles as the safe path
 * when a live model list is unavailable.
 */
export function RecommendedModels({ setup }: PartProps) {
  const { recommendedModels, values, form, preset } = setup;
  if (recommendedModels.length === 0) return null;

  const tiers: { tier: "paid" | "free"; label: string }[] = [
    { tier: "paid", label: "De pago" },
    { tier: "free", label: "Gratis" },
  ];

  return (
    <section style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: "1.1em", margin: "0 0 12px" }}>Modelos recomendados</h2>
      <p style={{ ...HINT, marginTop: 0 }}>
        Opciones pensadas para análisis de datos. Puedes usar un modelo gratuito o cargar
        créditos para los de pago.
      </p>
      {tiers.map(({ tier, label }) => {
        const models = recommendedModels.filter((m) => m.tier === tier);
        if (models.length === 0) return null;
        return (
          <div key={tier} style={{ marginBottom: 12 }}>
            <h3 style={{ fontSize: "0.95em", margin: "0 0 8px" }}>{label}</h3>
            {models.map((m) => {
              const selected = values.default_model === m.model;
              return (
                <button
                  key={m.model}
                  type="button"
                  onClick={() => form.setValue("default_model", m.model)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    marginBottom: 6,
                    padding: 12,
                    border: selected ? "2px solid #007acc" : "1px solid #ddd",
                    borderRadius: 4,
                    backgroundColor: selected ? "#eaf6ff" : "white",
                    cursor: "pointer",
                  }}
                >
                  <strong>{m.label}</strong>
                  {m.recommended && (
                    <span style={{ marginLeft: 8, color: "#007acc", fontSize: "0.8em" }}>
                      (Recomendado)
                    </span>
                  )}
                  <span style={{ display: "block", ...HINT }}>{priceLabel(m)}</span>
                </button>
              );
            })}
          </div>
        );
      })}
      <a
        href={recommendedModels[0].setupUrl}
        target="_blank"
        rel="noopener noreferrer"
        style={{ fontSize: "0.9em" }}
      >
        Obtener una clave de API en {preset?.label}
      </a>
    </section>
  );
}

/**
 * The default model.
 *
 * Restricted providers: the server whitelist is the list the chat-time gate
 * accepts; it arrives with the settings and cannot fail, so no fetch is needed
 * and no network error can leave the user with an empty list.
 *
 * Unrestricted providers (Groq / Ollama / LM Studio / Custom): they own their
 * catalog, so the live list is the only source of names — loaded on demand,
 * with free-text entry always available as the honest fallback.
 */
export function ModelField({ setup, id = "default-model" }: PartProps & { id?: string }) {
  const {
    form,
    isRestricted,
    modelOptions,
    recommendedModels,
    liveModels,
    visibleModels,
    modelsLoading,
    modelsError,
    refreshModels,
    modelQuery,
    setModelQuery,
    modelPlaceholder,
    preset,
  } = setup;

  const labelFor = (modelId: string) =>
    recommendedModels.find((m) => m.model === modelId)?.label ??
    liveModels.find((m) => m.id === modelId)?.name ??
    modelId;

  if (isRestricted) {
    return (
      <div style={{ marginBottom: 16 }}>
        <label htmlFor={id} style={FIELD_LABEL}>
          Modelo predeterminado
        </label>
        <select id={id} {...form.register("default_model")} style={INPUT}>
          <option value="">Predeterminado del servidor (variable OPENAI_MODEL)</option>
          {modelOptions.map((model) => (
            <option key={model} value={model}>
              {labelFor(model)}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 4,
        }}
      >
        <label htmlFor={id} style={{ display: "block" }}>
          Modelo predeterminado
        </label>
        <button
          type="button"
          onClick={() => refreshModels()}
          disabled={modelsLoading}
          style={LINK_BUTTON}
        >
          {modelsLoading ? COPY.STATUS.CHECKING : COPY.BUTTONS.LOAD_MODELS}
        </button>
      </div>

      {liveModels.length > 0 ? (
        <>
          <input
            type="text"
            value={modelQuery}
            onChange={(event) => setModelQuery(event.target.value)}
            placeholder={COPY.MODEL_SEARCH_PLACEHOLDER}
            style={{ ...INPUT, marginBottom: 8 }}
          />
          {visibleModels.length === 0 ? (
            <p style={HINT}>
              {COPY.MODEL_SEARCH_NO_RESULTS} "{modelQuery.trim()}".
            </p>
          ) : (
            <select id={id} {...form.register("default_model")} style={INPUT}>
              <option value="">{COPY.MODEL_REQUIRED}</option>
              {visibleModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          )}
        </>
      ) : (
        <>
          {modelsError && <p style={{ color: "orange", margin: "0 0 8px" }}>{COPY.MODEL_LIST_FALLBACK}</p>}
          {/* Keyless providers: the likely missing piece is the server itself,
              so say that instead of leaving the user guessing. */}
          {modelsError && preset && !preset.apiKeyRequired && (
            <p style={{ ...HINT, margin: "0 0 8px" }}>
              {COPY.MODEL_LOCAL_SERVER_HINT(preset.label)}
            </p>
          )}
          <input
            id={id}
            type="text"
            placeholder={modelPlaceholder}
            {...form.register("default_model")}
            style={INPUT}
          />
        </>
      )}
    </div>
  );
}

/** The honest result of a save: what was persisted, and whether it answered. */
export function SaveStatusLine({ setup }: PartProps) {
  const { status, statusDetail } = setup;
  if (status === "saved") return <p style={{ color: "green" }}>{COPY.STATUS.SAVED}</p>;
  if (status === "connected") return <p style={{ color: "green" }}>{COPY.STATUS.CONNECTED}</p>;
  if (status === "saved-unverified") {
    return (
      <p style={{ color: "red" }} role="alert">
        {COPY.STATUS.UNVERIFIED(statusDetail ?? "")}
      </p>
    );
  }
  if (status === "save-error") {
    return (
      <p style={{ color: "red" }} role="alert">
        {COPY.STATUS.SAVE_ERROR(statusDetail ?? "")}
      </p>
    );
  }
  return null;
}

/** Submit button that reports the save and the probe in flight. */
export function SaveButton({ setup, label }: PartProps & { label?: string }) {
  const busy = setup.status === "saving" || setup.status === "checking";
  const text =
    label ??
    (setup.status === "saving"
      ? COPY.STATUS.SAVING
      : setup.status === "checking"
        ? COPY.STATUS.CHECKING
        : COPY.BUTTONS.SAVE);
  return (
    <button type="submit" disabled={busy} style={{ padding: "8px 16px" }}>
      {text}
    </button>
  );
}
