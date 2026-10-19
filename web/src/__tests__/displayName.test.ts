import { describe, it, expect } from "vitest";
import { displayNameFromEmail } from "../lib/displayName";

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
