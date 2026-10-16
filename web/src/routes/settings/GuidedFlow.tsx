// The guided flow: provider -> credentials -> model, then the result.
//
// Three steps plus the outcome, not five. The connection test and the "done"
// screen stopped being steps because they are not decisions: the result of
// saving *is* the verification, and the honest save lifecycle already reports
// it ("Guardado · Conectado" / "Guardado, pero falló la conexión: …").
//
// The order is not cosmetic, it is the API's: POST /api/settings/models reads
// the *saved* provider, base URL and key (server/api/routers/settings.py), so
// credentials must be persisted before the flow can list models or probe the
// connection. That is also why credentials are saved when leaving step 2 while
// the model is saved at the end — the same two saves the old wizard did, minus
// the step that only asked the user to press a button.

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { COPY } from "../setup/copy";
import ProviderGuide from "./ProviderGuide";
import {
  ApiKeyField,
  BaseUrlField,
  KeylessProviderNote,
  ModelField,
  ProviderChoices,
  RecommendedModels,
  SaveStatusLine,
} from "./parts";
import type { ProviderSetup } from "./useProviderSetup";

const STEP_PROVIDER = 0;
const STEP_CREDENTIALS = 1;
const STEP_MODEL = 2;
const STEP_RESULT = 3;

interface GuidedFlowProps {
  setup: ProviderSetup;
  /**
   * "page" renders the standalone route (its own heading and an exit to
   * Ajustes); "embedded" is a mode inside the Ajustes screen.
   */
  layout?: "page" | "embedded";
  /** Called instead of navigating when the flow is embedded in a screen. */
  onExit?: () => void;
}

export default function GuidedFlow({ setup, layout = "page", onExit }: GuidedFlowProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState(STEP_PROVIDER);
  const [stepError, setStepError] = useState<string | null>(null);

  const exit = () => {
    if (onExit) onExit();
    else navigate("/app/settings");
  };

  const goNext = async () => {
    setStepError(null);
    const values = setup.form.getValues();

    if (step === STEP_PROVIDER) {
      const error = setup.validateProvider(values);
      if (error) {
        setStepError(error);
        return;
      }
      setStep(STEP_CREDENTIALS);
      return;
    }

    if (step === STEP_CREDENTIALS) {
      // The guided flow is where a key is being collected: an empty one must
      // not send the user forward with nothing.
      const error = setup.validateCredentials(values, true);
      if (error) {
        setStepError(error);
        return;
      }
      // Persist the credentials even if the user stops here: without them the
      // model step cannot list or probe anything.
      const result = await setup.persist("credentials");
      if (!result.ok) return; // the status line shows the reason; stay put
      setStep(STEP_MODEL);
      // Providers that own their catalog (Groq / Ollama / LM Studio) need the
      // live list; now that the key is stored, the server can fetch it.
      if (!setup.isRestricted) void setup.refreshModels();
      return;
    }

    if (step === STEP_MODEL) {
      const error = setup.validateModel(values);
      if (error) {
        setStepError(error);
        return;
      }
      await setup.persistAndProbe("model");
      setStep(STEP_RESULT);
    }
  };

  const goBack = () => {
    setStepError(null);
    setup.resetStatus();
    setStep((current) => Math.max(STEP_PROVIDER, current - 1));
  };

  const retryProbe = async () => {
    setStepError(null);
    await setup.persistAndProbe("model");
  };

  const busy = setup.status === "saving" || setup.status === "checking";
  const probeFailed = setup.status === "saved-unverified" || setup.status === "save-error";

  return (
    <div style={layout === "page" ? { maxWidth: 500, padding: 24 } : undefined}>
      {layout === "page" && <h1>Configuración del proveedor</h1>}

      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 24 }}>
        {COPY.GUIDED_STEPS.map((label, index) => (
          <div
            key={label}
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

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void goNext();
        }}
        noValidate
      >
        {step === STEP_PROVIDER && (
          <div>
            <h3>{COPY.GUIDED_STEPS[STEP_PROVIDER]}</h3>
            <ProviderChoices setup={setup} />
          </div>
        )}

        {step === STEP_CREDENTIALS && (
          <div>
            <h3>{COPY.GUIDED_STEPS[STEP_CREDENTIALS]}</h3>
            {setup.values.provider_type && (
              <ProviderGuide guideId={setup.values.provider_type} />
            )}
            <KeylessProviderNote setup={setup} />
            <BaseUrlField setup={setup} />
            <ApiKeyField setup={setup} />
          </div>
        )}

        {step === STEP_MODEL && (
          <div>
            <h3>{COPY.GUIDED_STEPS[STEP_MODEL]}</h3>
            <RecommendedModels setup={setup} />
            <ModelField setup={setup} />
          </div>
        )}

        {step === STEP_RESULT && (
          <div>
            <h3>{COPY.GUIDED_STEPS[STEP_RESULT]}</h3>
            {probeFailed && (
              <button
                type="button"
                onClick={() => void retryProbe()}
                disabled={busy}
                style={{ padding: "8px 16px", marginRight: 8 }}
              >
                {COPY.BUTTONS.RETRY}
              </button>
            )}
          </div>
        )}

        {stepError && (
          <p style={{ color: "red" }} role="alert">
            {stepError}
          </p>
        )}
        <SaveStatusLine setup={setup} />

        <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between" }}>
          <div>
            {step > STEP_PROVIDER && step < STEP_RESULT && (
              <button
                type="button"
                onClick={goBack}
                style={{ marginRight: 8, padding: "8px 16px" }}
              >
                {COPY.BUTTONS.PREVIOUS}
              </button>
            )}
            <button type="button" onClick={exit} style={{ padding: "8px 16px" }}>
              {layout === "page" ? COPY.BUTTONS.EXIT : "Volver a la vista completa"}
            </button>
          </div>

          <div>
            {step < STEP_MODEL && (
              <button
                type="submit"
                disabled={busy}
                style={{ padding: "8px 16px", backgroundColor: "#007acc", color: "white" }}
              >
                {COPY.BUTTONS.NEXT}
              </button>
            )}
            {step === STEP_MODEL && (
              <button
                type="submit"
                disabled={busy}
                style={{ padding: "8px 16px", backgroundColor: "#007acc", color: "white" }}
              >
                {COPY.BUTTONS.FINISH}
              </button>
            )}
            {step === STEP_RESULT && (
              <button
                type="button"
                onClick={() => navigate("/app/chat")}
                style={{ padding: "8px 16px", backgroundColor: "#007acc", color: "white" }}
              >
                Ir al chat
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
