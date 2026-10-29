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
