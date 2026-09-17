import { describe, it, expect } from "vitest";
import {
  NO_DATASET_CODE,
  resolveErrorPresentation,
  isKnownErrorCode,
} from "../lib/errorCodes";

const RETRY_PRESENTATION = {
  variant: "error",
  action: "retry-turn",
  actionLabel: "Reintentar",
} as const;

describe("resolveErrorPresentation", () => {
  it("maps auth codes to the go-settings danger presentation", () => {
    for (const code of ["auth/invalid_key", "auth/no_credits"]) {
      expect(resolveErrorPresentation(code)).toEqual({
        variant: "error",
        title: "Error de autenticación",
        action: "go-settings",
        actionLabel: "Ir a Ajustes",
      });
    }
  });

  it("maps model/not_allowed to the warning presentation without action", () => {
    expect(resolveErrorPresentation("model/not_allowed")).toEqual({
      variant: "warning",
      title: "Modelo no disponible",
      action: "none",
      actionLabel: undefined,
    });
  });

  it.each([
    "sandbox/runtime_error",
    "sandbox/syntax_error",
    "sandbox/import_error",
    "sandbox/memory",
    "sandbox/timeout",
  ])("maps %s to the execution-error retry presentation", (code) => {
    expect(resolveErrorPresentation(code)).toEqual({
      ...RETRY_PRESENTATION,
      title: "Error de ejecución",
    });
  });

  it.each(["llm/invalid_json", "llm/timeout", "llm/rate_limit"])(
    "maps %s to the model-error retry presentation",
    (code) => {
      expect(resolveErrorPresentation(code)).toEqual({
        ...RETRY_PRESENTATION,
        title: "Error del modelo",
      });
    },
  );

  it("maps internal/error (Enmienda 1) to the generic danger retry presentation", () => {
    expect(resolveErrorPresentation("internal/error")).toEqual({
      ...RETRY_PRESENTATION,
      title: "Error",
    });
  });

  it("maps session/no_dataset to the info retry presentation", () => {
    expect(resolveErrorPresentation(NO_DATASET_CODE)).toEqual({
      variant: "info",
      title: "Esta sesión no tiene datos",
      action: "retry-turn",
      actionLabel: "Reintentar",
    });
  });

  it.each(["model/inadequate", "weird/unrecognized", null, undefined])(
    "degrades unknown/missing code %s to the generic danger fallback",
    (code) => {
      expect(resolveErrorPresentation(code)).toEqual({
        ...RETRY_PRESENTATION,
        title: "Error",
      });
    },
  );
});

describe("isKnownErrorCode", () => {
  it.each([
    "auth/invalid_key",
    "auth/no_credits",
    "model/not_allowed",
    "sandbox/timeout",
    "llm/rate_limit",
    "internal/error",
    "session/no_dataset",
  ])("recognizes taxonomy code %s", (code) => {
    expect(isKnownErrorCode(code)).toBe(true);
  });

  it.each(["model/inadequate", "nope/unknown", null, undefined])(
    "rejects non-taxonomy/missing code %s",
    (code) => {
      expect(isKnownErrorCode(code)).toBe(false);
    },
  );
});
