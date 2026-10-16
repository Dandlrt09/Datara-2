// The Ajustes screen, rendered over the shared engine.
//
// What it shows depends on the variant under experiment (`variant.ts`):
//   a — a switch between the guided flow and this full view
//   b — only this full view
//   c — this full view, plus the link to the standalone guided route
//
// The fields themselves are the same in all three: the variants change how the
// user arrives at them, not what they do. That is the point of the experiment —
// comparing arrangements, not comparing rules.

import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
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
import { readSettingsVariant } from "./settings/variant";

type Mode = "guiado" | "avanzado";

/**
 * Every field at once, with one save: the view a user reaches to change a
 * detail once the app already works. No client-side validation here — the user
 * is in control and the server is the authority on what it accepts (this is
 * the old hub's contract, kept).
 */
function AdvancedView({ setup }: { setup: ProviderSetup }) {
  return (
    <QueryError error={setup.settingsError} onRetry={setup.refetchSettings}>
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
    </QueryError>
  );
}

export default function SettingsView() {
  const [params] = useSearchParams();
  const variant = readSettingsVariant(params.get("variante"));
  const setup = useProviderSetup();
  // Once the user picks a mode, that choice wins; until then an app with
  // nothing configured opens the guided flow and a configured one opens the
  // full view (S5).
  const [chosenMode, setChosenMode] = useState<Mode | null>(null);

  if (setup.isLoading) return <p>Cargando ajustes...</p>;

  const mode: Mode = chosenMode ?? (setup.isConfigured ? "avanzado" : "guiado");
  const guided = variant === "a" && mode === "guiado";

  return (
    <div style={{ maxWidth: 500 }}>
      <h1>Ajustes</h1>

      {variant === "a" && (
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
      )}

      {variant === "c" && (
        <div style={{ marginBottom: 16 }}>
          <Link
            to="/app/setup?variante=c"
            style={{
              display: "inline-block",
              padding: "8px 16px",
              backgroundColor: "#007acc",
              color: "white",
              borderRadius: 4,
              textDecoration: "none",
            }}
          >
            Configurar paso a paso
          </Link>
        </div>
      )}

      {guided ? (
        <GuidedFlow setup={setup} layout="embedded" onExit={() => setChosenMode("avanzado")} />
      ) : (
        <AdvancedView setup={setup} />
      )}
    </div>
  );
}
