import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { useSettings, useUpdateSettings } from "../queries/useSettings";
import { COPY } from "./setup/copy";
import { PRESETS } from "./setup/presets";
import { useFetchModels } from "./setup/useFetchModels";

type ProviderType = "openrouter" | "ollama" | "lmstudio" | "groq" | "custom";

interface WizardForm {
  providerType: string;
  baseUrl: string;
  apiKey: string;
  model: string;
}

interface SaveError {
  code?: string;
}

// Pull the error code (if any) out of an ApiError thrown by useUpdateSettings.
function extractSaveError(err: unknown): SaveError {
  const anyErr = err as { body?: { detail?: { code?: string } } } | undefined;
  return anyErr?.body?.detail ?? {};
}

export default function Setup() {
  const navigate = useNavigate();
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();

  // Route-scoped step machine: provider -> credentials -> model -> test -> done.
  const [step, setStep] = useState(0);
  const [connectionTestPassed, setConnectionTestPassed] = useState(false);
  const [saveError, setSaveError] = useState<SaveError | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    reset,
    setValue,
    formState: { errors },
  } = useForm<WizardForm>({
    defaultValues: {
      providerType: "",
      baseUrl: "",
      apiKey: "",
      model: "",
    },
  });

  const {
    models,
    isLoading: modelsLoading,
    error: modelsError,
    fetchModels,
  } = useFetchModels();

  const formValues = watch();
  const selectedPreset = PRESETS.find((p) => p.id === formValues.providerType);

  // Prefill from saved settings on load (re-entry always starts at the provider
  // step pre-filled from current settings; there is no server-side wizard state).
  useEffect(() => {
    if (settings) {
      reset({
        providerType: settings.provider_type || "",
        baseUrl: settings.base_url || "",
        apiKey: "",
        model: settings.default_model || "",
      });
    }
  }, [settings, reset]);

  // Switching presets mid-wizard resets base_url to the new preset's default
  // (stale-URL prevention) and clears the model. The ref distinguishes the
  // initial load (keep saved base_url) from a user-driven preset switch.
  const prevProviderRef = useRef<string | null>(null);
  useEffect(() => {
    const current = formValues.providerType;
    if (prevProviderRef.current === null) {
      prevProviderRef.current = current;
      return;
    }
    if (prevProviderRef.current === current) return;
    prevProviderRef.current = current;
    const preset = PRESETS.find((p) => p.id === current);
    setValue("baseUrl", preset ? preset.defaultBaseUrl : "");
    setValue("model", "");
    setConnectionTestPassed(false);
  }, [formValues.providerType, setValue]);

  // Named presets fetch the live model list on entering the model step;
  // Custom preset uses free-text entry only (no fetch).
  useEffect(() => {
    if (step === 2 && formValues.providerType && formValues.providerType !== "custom") {
      fetchModels();
    }
  }, [step, formValues.providerType, fetchModels]);

  // Connection test: cost-zero probe of the model-fetch endpoint (no LLM call).
  const runConnectionTest = () => {
    fetchModels()
      .then((result) => setConnectionTestPassed(!result.error))
      .catch(() => setConnectionTestPassed(false));
  };

  // Run the probe automatically when entering the test step.
  useEffect(() => {
    if (step === 3) runConnectionTest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const goNext = async (data: WizardForm) => {
    if (step === 1) {
      // Credentials step saves provider_type + base_url + api_key.
      try {
        await updateSettings.mutateAsync({
          provider_type: (data.providerType || null) as ProviderType | null,
          base_url: data.baseUrl.trim() || null,
          ...(data.apiKey.trim() ? { api_key: data.apiKey.trim() } : {}),
        });
      } catch (err) {
        setSaveError(extractSaveError(err));
        return; // validation/save failed (e.g. SSRF 422): stay on this step
      }
    } else if (step === 2) {
      // Model step saves default_model.
      try {
        await updateSettings.mutateAsync({ default_model: data.model.trim() });
      } catch (err) {
        setSaveError(extractSaveError(err));
        return;
      }
    }
    setSaveError(null);
    if (step < 4) setStep(step + 1);
  };

  if (isLoading) {
    return <div>Cargando...</div>;
  }

  return (
    <div style={{ maxWidth: 500, padding: 24 }}>
      <h1>Configuración del proveedor</h1>

      {/* Step indicator */}
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 24 }}>
        {COPY.STEPS.map((label, index) => (
          <div
            key={index}
            style={{
              textAlign: "center",
              flex: 1,
              padding: 8,
              backgroundColor: index === step ? "#007acc" : "#f0f0f0",
              color: index === step ? "white" : "#666",
              fontWeight: index === step ? "bold" : "normal",
              borderRadius: 4,
              margin: "0 4px",
            }}
          >
            {label}
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit(goNext)} noValidate>
        {/* Step 0: Provider selection */}
        {step === 0 && (
          <div>
            <div style={{ marginBottom: 16 }}>
              {PRESETS.map((preset) => (
                <div key={preset.id} style={{ marginBottom: 8 }}>
                  <label>
                    <input
                      type="radio"
                      value={preset.id}
                      {...register("providerType", { required: true })}
                    />
                    {" "}
                    {preset.label}
                    {preset.apiKeyRequired && " (clave de API requerida)"}
                  </label>
                  {formValues.providerType === preset.id && preset.defaultBaseUrl && (
                    <div style={{ marginLeft: 24, fontSize: "0.9em", color: "#666" }}>
                      URL predeterminada: {preset.defaultBaseUrl}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {errors.providerType && (
              <p style={{ color: "red" }} role="alert">
                Selecciona un proveedor
              </p>
            )}
          </div>
        )}

        {/* Step 1: Credentials */}
        {step === 1 && (
          <div>
            <h3>{COPY.STEPS[1]}</h3>
            {selectedPreset?.id === "custom" && (
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", marginBottom: 4 }}>
                  URL base *
                </label>
                <input
                  type="text"
                  {...register("baseUrl", { required: true })}
                  placeholder="https://..."
                  style={{ width: "100%", padding: 8 }}
                />
                {errors.baseUrl && (
                  <p style={{ color: "red", fontSize: "0.9em" }}>{COPY.BASE_URL_REQUIRED}</p>
                )}
              </div>
            )}

            {selectedPreset?.apiKeyRequired && (
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", marginBottom: 4 }}>
                  Clave de API *
                </label>
                <input
                  type="password"
                  {...register("apiKey", { required: true })}
                  placeholder="sk-..."
                  style={{ width: "100%", padding: 8 }}
                />
                {errors.apiKey && (
                  <p style={{ color: "red", fontSize: "0.9em" }}>{COPY.KEY_REQUIRED}</p>
                )}
              </div>
            )}

            {saveError && (
              <p style={{ color: "red" }} role="alert">
                {saveError.code === "invalid_base_url"
                  ? COPY.SSRF_REJECTION
                  : "Error al guardar configuración"}
              </p>
            )}
          </div>
        )}

        {/* Step 2: Model selection */}
        {step === 2 && (
          <div>
            <h3>Modelo predeterminado</h3>

            {modelsLoading ? (
              <p>Cargando modelos...</p>
            ) : selectedPreset?.id === "custom" ? (
              // Custom preset: free-text entry only, no fetch attempted.
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", marginBottom: 4 }}>
                  Identificador del modelo *
                </label>
                <input
                  type="text"
                  {...register("model", { required: true })}
                  placeholder="gpt-4o, llama3.2:latest, etc."
                  style={{ width: "100%", padding: 8 }}
                />
              </div>
            ) : modelsError || models.length === 0 ? (
              // Fetch error or empty list: free-text fallback with the spec copy.
              <div>
                <p style={{ color: "orange" }}>{COPY.MODEL_LIST_FALLBACK}</p>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: "block", marginBottom: 4 }}>
                    Identificador del modelo *
                  </label>
                  <input
                    type="text"
                    {...register("model", { required: true })}
                    placeholder="gpt-4o, llama3.2:latest, etc."
                    style={{ width: "100%", padding: 8 }}
                  />
                </div>
              </div>
            ) : (
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", marginBottom: 4 }}>
                  Selecciona un modelo
                </label>
                <select
                  {...register("model", { required: true })}
                  style={{ width: "100%", padding: 8 }}
                >
                  <option value="">{COPY.MODEL_REQUIRED}</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {errors.model && (
              <p style={{ color: "red", fontSize: "0.9em" }}>{COPY.MODEL_REQUIRED}</p>
            )}
          </div>
        )}

        {/* Step 3: Connection test */}
        {step === 3 && (
          <div>
            <h3>{COPY.STEPS[3]}</h3>

            <div
              style={{
                padding: 16,
                backgroundColor: connectionTestPassed ? "#e6f7e6" : "#fff3cd",
                borderRadius: 4,
                marginBottom: 16,
              }}
            >
              {modelsLoading ? (
                <p>Verificando conexión con el proveedor...</p>
              ) : connectionTestPassed ? (
                <p style={{ color: "green" }}>Conexión exitosa.</p>
              ) : (
                <div>
                  <p style={{ color: "red" }}>{COPY.TEST_FAILED}</p>
                  {modelsError && (
                    <p style={{ fontSize: "0.9em", color: "#666" }}>
                      Error: {modelsError.message}
                    </p>
                  )}
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={runConnectionTest}
              disabled={modelsLoading}
              style={{ marginRight: 8, padding: "8px 16px" }}
            >
              {COPY.BUTTONS.RETRY}
            </button>
          </div>
        )}

        {/* Step 4: Done */}
        {step === 4 && (
          <div>
            <h3>{COPY.STEPS[4]}</h3>
            <div
              style={{
                padding: 16,
                backgroundColor: "#e6f7e6",
                borderRadius: 4,
                marginBottom: 16,
              }}
            >
              <p style={{ color: "green" }}>{COPY.DONE_CONFIRMATION}</p>
            </div>
          </div>
        )}

        {/* Navigation buttons */}
        <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between" }}>
          <div>
            {step > 0 && step < 4 && (
              <button
                type="button"
                onClick={() => setStep(step - 1)}
                style={{ marginRight: 8, padding: "8px 16px" }}
              >
                {COPY.BUTTONS.PREVIOUS}
              </button>
            )}
            <button
              type="button"
              onClick={() => navigate("/app/settings")}
              style={{ padding: "8px 16px" }}
            >
              {COPY.BUTTONS.EXIT}
            </button>
          </div>

          <div>
            {step < 4 && (
              <button
                type="submit"
                disabled={step === 3 && (!connectionTestPassed || modelsLoading)}
                style={{ padding: "8px 16px", backgroundColor: "#007acc", color: "white" }}
              >
                {step === 3 ? COPY.BUTTONS.FINISH : COPY.BUTTONS.NEXT}
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}