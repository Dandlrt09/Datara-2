import { describe, it, expect } from "vitest";
import { displayNameFromEmail, resolveDisplayName } from "../lib/displayName";

describe("displayNameFromEmail", () => {
  it("returns the local part of a normal email", () => {
    expect(displayNameFromEmail("dan@datara.ai")).toBe("dan");
  });

  it("trims surrounding whitespace before deriving the name", () => {
    expect(displayNameFromEmail("  dan@datara.ai  ")).toBe("dan");
  });

  it("returns the input when there is no @", () => {
    expect(displayNameFromEmail("dan")).toBe("dan");
  });

  it("returns the trimmed input when the local part is empty", () => {
    expect(displayNameFromEmail("@datara.ai")).toBe("@datara.ai");
  });

  it("falls back to Cuenta for an empty or whitespace-only value", () => {
    expect(displayNameFromEmail("")).toBe("Cuenta");
    expect(displayNameFromEmail("   ")).toBe("Cuenta");
  });
});

/**
 * T1/D6: one helper decides what the profile and the sidebar print, so the two
 * screens can never disagree. A chosen name wins; anything empty is "no name",
 * which is the email-derived fallback.
 */
describe("resolveDisplayName", () => {
  it("prefers the chosen name over the email", () => {
    expect(resolveDisplayName("Daniel", "dan@datara.ai")).toBe("Daniel");
  });

  it("trims the chosen name before showing it", () => {
    expect(resolveDisplayName("  Daniel  ", "dan@datara.ai")).toBe("Daniel");
  });

  it("falls back to the email local part when the name is null", () => {
    expect(resolveDisplayName(null, "dan@datara.ai")).toBe("dan");
  });

  it("falls back when the name is empty or only spaces", () => {
    expect(resolveDisplayName("", "dan@datara.ai")).toBe("dan");
    expect(resolveDisplayName("   ", "dan@datara.ai")).toBe("dan");
  });

  it("falls back when the user payload carries no name at all", () => {
    expect(resolveDisplayName(undefined, "dan@datara.ai")).toBe("dan");
  });
});

/**
 * F1/T5: a local profile has no address at all, so `email` is null. The name
 * is required when a local profile is created (D5), so a real local user never
 * needs the email; the resolver still has to stay total and must never
 * fabricate an address. The final branch covers the partial payloads the
 * screens see while the user loads.
 */
describe("resolveDisplayName without an address", () => {
  it("prefers the chosen name when there is no email", () => {
    expect(resolveDisplayName("Ana", null)).toBe("Ana");
    expect(resolveDisplayName("  Ana  ", null)).toBe("Ana");
  });

  it("falls back to a person-like default with neither name nor email", () => {
    expect(resolveDisplayName(null, null)).toBe("Analista");
    expect(resolveDisplayName(undefined, null)).toBe("Analista");
    expect(resolveDisplayName("", null)).toBe("Analista");
    expect(resolveDisplayName("   ", null)).toBe("Analista");
  });

  it("treats a blank email as no email, never as an address", () => {
    expect(resolveDisplayName(null, "")).toBe("Analista");
    expect(resolveDisplayName(null, "   ")).toBe("Analista");
  });

  it("keeps deriving from the email when one is present", () => {
    expect(resolveDisplayName(null, "dan@datara.ai")).toBe("dan");
  });

  it("never returns the string 'null'", () => {
    expect(resolveDisplayName(null, null)).not.toBe("null");
  });
});
