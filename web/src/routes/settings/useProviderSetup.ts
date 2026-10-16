// One engine for provider configuration, shared by every screen variant.
//
// Before this file, `routes/Setup.tsx` (wizard) and `routes/SettingsView.tsx`
// (hub) each reimplemented the same rules: which provider is selected, whether
// the model comes from the server whitelist or from free text, when to save,
// and what "saved" is allowed to claim. Two copies of a rule are two chances to
// diverge, and no test checked that the two screens agreed.
//
// The rules that live here (and therefore nowhere else):
//   - prefill from saved settings, keeping a stored provider that no preset
//     carries instead of silently dropping it (S4)
//   - switching provider resets base_url to the preset default and clears the
//     model (stale-URL prevention)
//   - the model gate mirror decides list vs free text (`modelGate.ts`)
//   - the honest save lifecycle: PUT first, probe after, and never claim
//     "Connected" without a successful probe
//   - validation of the provider, the credentials and the model
//
// Presentation stays in the screens. Paths keep living under `routes/settings/`
// while `routes/setup/` still holds the shared data files (`presets.ts`,
// `copy.ts`, `useFetchModels.ts`): the wizard route only disappears in the
// variants the maintainer has not chosen yet.

import { useCallback, useEffect, useRef, useState } from "react";
import { useForm, type UseFormReturn } from "react-hook-form";
import {
  useSettings,
  useUpdateSettings,
  type UserSettings,
} from "../../queries/useSettings";
import { COPY } from "../setup/copy";
import { PRESETS } from "../setup/presets";
import {
  useFetchModels,
  type ModelInfo,
  type ModelsResponse,
} from "../setup/useFetchModels";
import { isModelRestricted } from "./modelGate";
import { modelsForProvider, type RecommendedModel } from "./recommended";

export type ProviderId =
  | "openrouter"
  | "ollama"
  | "lmstudio"
  | "groq"
  | "custom";

export interface ProviderForm {
  provider_type: string;
  base_url: string;
  api_key: string;
  default_model: string;
}

export type SaveStatus =
  | "idle"
  | "saving"
  | "checking"
  | "saved"
  | "connected"
  | "saved-unverified"
  | "save-error";

/** Which part of the configuration a save covers. */
export type SaveScope = "credentials" | "model" | "all";

/** A save either reports the server's answer or a message fit for the user. */
export type SaveResult =
  | { ok: true; saved: UserSettings }
  | { ok: false; message: string };

/**
 * One selectable provider: a shipped preset, or a stored value that no preset
 * carries (S4 — shown as an option instead of being dropped).
 */
export interface ProviderOption {
  id: string;
  label: string;
  defaultBaseUrl: string;
  apiKeyRequired: boolean;
  legacy: boolean;
}

/** Extract a human-readable reason from an ApiError (FastAPI 422 detail).
 *
 * Three detail shapes reach here: a plain string, FastAPI's validation list of
 * {msg}, and the domain rejection object {code, message} the SSRF guard raises
 * (BaseUrlRejected). The last one must not surface as a bare "API error 422":
 * known codes map to the same Spanish copy the screens show.
 */
export function saveErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "body" in error) {
    const detail = (error as { body?: { detail?: unknown } }).body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object") {
      return String((detail[0] as { msg?: unknown }).msg ?? "invalid value");
    }
    if (detail && typeof detail === "object") {
      const code = (detail as { code?: unknown }).code;
      if (code === "invalid_base_url") return COPY.SSRF_REJECTION;
    }
  }
  return error instanceof Error ? error.message : "unknown error";
}

export interface ProviderSetup {
  settings: UserSettings | undefined;
  isLoading: boolean;

  form: UseFormReturn<ProviderForm>;
  values: ProviderForm;
  providerOptions: ProviderOption[];
  preset: ProviderOption | undefined;
  presetDefault: string;
  hasPresetDefault: boolean;
  chooseProvider(id: string): void;
  /** Manual URL override: a preset URL is locked until the user asks to edit it. */
  urlUnlocked: boolean;
  unlockUrl(): void;
  lockUrl(): void;
  restorePresetDefaultUrl(): void;

  isRestricted: boolean;
  allowedModels: string[];
  modelOptions: string[];
  recommendedModels: RecommendedModel[];

  liveModels: ModelInfo[];
  modelsLoading: boolean;
  modelsError: Error | null;
  refreshModels(): Promise<ModelsResponse>;
  modelQuery: string;
  setModelQuery(query: string): void;
  visibleModels: ModelInfo[];

  validateProvider(values: ProviderForm): string | null;
  validateCredentials(values: ProviderForm): string | null;
  validateModel(values: ProviderForm): string | null;

  persist(scope: SaveScope): Promise<SaveResult>;
  persistAndProbe(scope: SaveScope): Promise<SaveResult>;

  status: SaveStatus;
  statusDetail: string | null;
  resetStatus(): void;
}

export function useProviderSetup(): ProviderSetup {
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();
  const {
    models,
    isLoading: modelsLoading,
    error: modelsError,
    fetchModels,
  } = useFetchModels();

  const form = useForm<ProviderForm>({
    defaultValues: {
      provider_type: "",
      base_url: "",
      api_key: "",
      default_model: "",
    },
  });
  const { watch, setValue, reset } = form;

  const [modelQuery, setModelQuery] = useState("");
  const [urlUnlocked, setUrlUnlocked] = useState(false);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [statusDetail, setStatusDetail] = useState<string | null>(null);

  // A stored provider that no preset carries (S4). The server type is a
  // Literal over the five presets, so this only happens for a value written by
  // an older or different server — cheap insurance, and it keeps the two
  // screens from disagreeing about the same row.
  const storedProvider = settings?.provider_type ?? "";
  const legacyProvider =
    storedProvider !== "" && !PRESETS.some((p) => p.id === storedProvider)
      ? storedProvider
      : null;

  const providerOptions: ProviderOption[] = [
    ...PRESETS.map((p) => ({ ...p, legacy: false })),
    ...(legacyProvider
      ? [
          {
            id: legacyProvider,
            label: COPY.LEGACY_PROVIDER_LABEL(legacyProvider),
            defaultBaseUrl: "",
            apiKeyRequired: true,
            legacy: true,
          },
        ]
      : []),
  ];

  // Prefill once per mount, when settings first arrive. React Query refetches
  // on window focus and after every save; re-prefilling on each response would
  // wipe whatever the user is typing, so the saved truth reaches the user
  // through the status line instead.
  const prefilled = useRef(false);
  useEffect(() => {
    if (!settings || prefilled.current) return;
    prefilled.current = true;
    const stored = settings.provider_type ?? "";
    const storedPreset = PRESETS.find((p) => p.id === stored);
    setUrlUnlocked(false);
    reset({
      // S4: a stored value is never replaced by "" here; an unknown one is
      // carried by the legacy option above.
      provider_type: stored,
      // A saved URL wins, including a gateway override; the preset default
      // fills in when nothing was saved.
      base_url: settings.base_url ?? storedPreset?.defaultBaseUrl ?? "",
      api_key: "",
      default_model: settings.default_model ?? "",
    });
  }, [settings, reset]);

  const values = watch();
  const preset = providerOptions.find((p) => p.id === values.provider_type);
  const presetDefault = preset?.defaultBaseUrl ?? "";
  const hasPresetDefault = presetDefault !== "";
  const isRestricted = isModelRestricted(values.provider_type);
  const allowedModels = settings?.allowed_models ?? [];
  const recommendedModels = modelsForProvider(values.provider_type);

  const chooseProvider = useCallback(
    (id: string) => {
      const next = PRESETS.find((p) => p.id === id);
      setValue("provider_type", id);
      setValue("base_url", next?.defaultBaseUrl ?? "");
      setValue("default_model", "");
      setModelQuery("");
      // A new provider means a new default URL: a manual override from the
      // previous provider must not leak into it.
      setUrlUnlocked(false);
      setStatus("idle");
      setStatusDetail(null);
    },
    [setValue],
  );

  const unlockUrl = useCallback(() => setUrlUnlocked(true), []);
  const lockUrl = useCallback(() => setUrlUnlocked(false), []);
  const restorePresetDefaultUrl = useCallback(
    () => setValue("base_url", presetDefault),
    [setValue, presetDefault],
  );

  // Dropdown options: the server whitelist, plus a stored model that predates
  // it, so the current selection is never lost.
  const modelOptions =
    settings?.default_model && !allowedModels.includes(settings.default_model)
      ? [settings.default_model, ...allowedModels]
      : allowedModels;

  // Live list: restricted providers show only the whitelisted ids; the others
  // own their catalog. An empty whitelist filters nothing — the chat-time gate
  // and its recovery banner remain the backstop.
  const selectableModels = isRestricted
    ? models.filter((m) => allowedModels.includes(m.id))
    : models;
  const normalizedQuery = modelQuery.trim().toLowerCase();
  const visibleModels =
    normalizedQuery === ""
      ? selectableModels
      : selectableModels.filter(
          (m) =>
            m.id.toLowerCase().includes(normalizedQuery) ||
            m.name.toLowerCase().includes(normalizedQuery),
        );

  const refreshModels = useCallback(() => fetchModels(), [fetchModels]);

  const validateProvider = (v: ProviderForm) =>
    v.provider_type ? null : COPY.PROVIDER_REQUIRED;

  const validateCredentials = (v: ProviderForm) => {
    const option = providerOptions.find((p) => p.id === v.provider_type);
    if (!option) return COPY.PROVIDER_REQUIRED;
    if (option.id === "custom" && !v.base_url.trim()) return COPY.BASE_URL_REQUIRED;
    // A stored key counts: re-entering the flow must not force retyping a key
    // the server already holds (the PUT keeps it when api_key is omitted).
    const hasStoredKey = settings?.has_api_key === true;
    if (option.apiKeyRequired && !v.api_key.trim() && !hasStoredKey) {
      return COPY.KEY_REQUIRED;
    }
    return null;
  };

  const validateModel = (v: ProviderForm) => {
    const model = v.default_model.trim();
    if (!model) return COPY.MODEL_REQUIRED;
    // Only enforce the whitelist when it is known: an absent or empty whitelist
    // must not dead-end the flow.
    if (
      isModelRestricted(v.provider_type) &&
      allowedModels.length > 0 &&
      !allowedModels.includes(model)
    ) {
      return COPY.MODEL_NOT_ALLOWED;
    }
    return null;
  };

  const buildPayload = (v: ProviderForm, scope: SaveScope) => {
    const payload: Parameters<typeof updateSettings.mutateAsync>[0] = {};
    if (scope !== "model") {
      payload.provider_type = (v.provider_type || null) as ProviderId | null;
      // An empty base_url clears the stored one on the server (the API
      // documents an empty string as "clear").
      payload.base_url = v.base_url.trim();
      const key = v.api_key.trim();
      // Omitting the key keeps the stored one (server-side COALESCE).
      if (key) payload.api_key = key;
    }
    if (scope !== "credentials") {
      const model = v.default_model.trim();
      if (model) payload.default_model = model;
    }
    return payload;
  };

  const persist = async (scope: SaveScope): Promise<SaveResult> => {
    setStatus("saving");
    setStatusDetail(null);
    try {
      const saved = await updateSettings.mutateAsync(
        buildPayload(form.getValues(), scope),
      );
      // The server now holds the key; the input must not keep showing it as
      // if it still had to be sent.
      if (scope !== "model") setValue("api_key", "");
      return { ok: true, saved };
    } catch (err) {
      const message = saveErrorMessage(err);
      setStatus("save-error");
      setStatusDetail(message);
      return { ok: false, message };
    }
  };

  const persistAndProbe = async (scope: SaveScope): Promise<SaveResult> => {
    const result = await persist(scope);
    if (!result.ok) return result;

    // Trust the server-returned provider_type; fall back to the submitted
    // value when the response omits it. A falsy value means the provider was
    // cleared: there is nothing to verify, so a plain success is honest.
    const effectiveProvider =
      result.saved?.provider_type ?? form.getValues().provider_type ?? null;
    if (!effectiveProvider) {
      setStatus("saved");
      return result;
    }

    setStatus("checking");
    try {
      const res = await fetchModels();
      if (res.error == null) {
        setStatus("connected");
        setStatusDetail(null);
      } else {
        setStatus("saved-unverified");
        setStatusDetail(res.error.message);
      }
    } catch (err) {
      setStatus("saved-unverified");
      setStatusDetail(err instanceof Error ? err.message : "unknown error");
    }
    return result;
  };

  const resetStatus = useCallback(() => {
    setStatus("idle");
    setStatusDetail(null);
  }, []);

  return {
    settings,
    isLoading,
    form,
    values,
    providerOptions,
    preset,
    presetDefault,
    hasPresetDefault,
    chooseProvider,
    urlUnlocked,
    unlockUrl,
    lockUrl,
    restorePresetDefaultUrl,
    isRestricted,
    allowedModels,
    modelOptions,
    recommendedModels,
    liveModels: models,
    modelsLoading,
    modelsError,
    refreshModels,
    modelQuery,
    setModelQuery,
    visibleModels,
    validateProvider,
    validateCredentials,
    validateModel,
    persist,
    persistAndProbe,
    status,
    statusDetail,
    resetStatus,
  };
}
