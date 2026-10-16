// The Ajustes screen: one screen, two modes.
//
// "Guiado" walks provider -> credentials -> model with the shared engine;
// "Avanzado" puts every field at once with a single save. Both modes render the
// same pieces (`parts.tsx`) over the same rules (`useProviderSetup.ts`), so a
// rule fixed once is fixed in both.
//
// This arrangement is the one the Ronda 10 usability pass chose (see
// `~/OneDrive/Escritorio/datara-validaciones-beta.txt`); the two arrangements it
// beat were deleted with their scaffolding, and the mode no longer depends on
// any URL parameter.

import { useEffect, useState } from "react";
import { QueryError } from "../components/ErrorCard";
import GuidedFlow from "./settings/GuidedFlow";
import ProviderGuide from "./settings/ProviderGuide";
import {
  ApiKeyField,
  BaseUrlField,
  KeylessProviderNote,
  ModelField,
  ProviderSelect,
  RecommendedModels,
  SaveButton,
  SaveStatusLine,
} from "./settings/parts";
import { useProviderSetup, type ProviderSetup } from "./settings/useProviderSetup";

type Mode = "guiado" | "avanzado";

/**
 * Every field at once, with one save: the view a user reaches to change a
 * detail once the app already works. No client-side validation here — the user
 * is in control and the server is the authority on what it accepts (this is
 * the old hub's contract, kept).
 */
function AdvancedView({ setup }: { setup: ProviderSetup }) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void setup.persistAndProbe("all");
      }}
      noValidate
    >
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: "1.1em", margin: "0 0 12px" }}>Proveedor de LLM</h2>
        <ProviderSelect setup={setup} />
        <BaseUrlField setup={setup} />
        <ApiKeyField setup={setup} />
        <KeylessProviderNote setup={setup} />
      </section>
      {setup.values.provider_type && (
        <ProviderGuide guideId={setup.values.provider_type} />
      )}
      <RecommendedModels setup={setup} />
      <ModelField setup={setup} />
      <SaveStatusLine setup={setup} />
      <SaveButton setup={setup} />
    </form>
  );
}

export default function SettingsView() {
  const setup = useProviderSetup();
  // Once the user picks a mode, that choice wins; until then an app with
  // nothing configured opens the guided flow and a configured one opens the
  // full view (S5).
  const [chosenMode, setChosenMode] = useState<Mode | null>(null);
  // The default is decided ONCE, as soon as settings are known, and then never
  // re-derived: the guided flow configures the provider itself, so the instant
  // its credentials save succeeds "is it configured?" flips to true and a
  // re-derived mode would switch the screen to the full view, cutting the
  // step-by-step in half (found in the Ronda 10 usability pass, O10).
  const [initialMode, setInitialMode] = useState<Mode | null>(null);
  useEffect(() => {
    if (initialMode === null && !setup.isLoading) {
      setInitialMode(setup.isConfigured ? "avanzado" : "guiado");
    }
  }, [initialMode, setup.isLoading, setup.isConfigured]);

  if (setup.isLoading) return <p>Cargando ajustes...</p>;

  // The derived value is only the fallback for the first render with settings,
  // so a configured app never flashes the guided flow.
  const mode: Mode =
    chosenMode ?? initialMode ?? (setup.isConfigured ? "avanzado" : "guiado");
  const guided = mode === "guiado";

  return (
    <div style={{ maxWidth: 500 }}>
      <h1>Ajustes</h1>

      {/* One failure surface for both modes: the guided flow also needs the
          stored settings (the stored key, the whitelist, the saved row), so a
          failed query must not let it render blind. */}
      <QueryError error={setup.settingsError} onRetry={setup.refetchSettings}>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["guiado", "avanzado"] as Mode[]).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setChosenMode(value)}
            aria-pressed={mode === value}
            style={{
              padding: "6px 12px",
              borderRadius: 4,
              border: mode === value ? "2px solid #007acc" : "1px solid #ccc",
              backgroundColor: mode === value ? "#eaf6ff" : "white",
              cursor: "pointer",
            }}
          >
            {value === "guiado" ? "Guiado" : "Avanzado"}
          </button>
        ))}
      </div>

      {guided ? (
        <GuidedFlow setup={setup} layout="embedded" onExit={() => setChosenMode("avanzado")} />
      ) : (
        <AdvancedView setup={setup} />
      )}
      </QueryError>
    </div>
  );
}
