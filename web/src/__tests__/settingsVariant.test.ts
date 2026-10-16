import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import {
  DEFAULT_SETTINGS_VARIANT,
  readSettingsVariant,
  storedSettingsVariant,
} from "../routes/settings/variant";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("settings variant selection", () => {
  it("uses the default when nothing was asked for", () => {
    expect(readSettingsVariant(null)).toBe(DEFAULT_SETTINGS_VARIANT);
    expect(storedSettingsVariant()).toBeNull();
  });

  it("lets the query parameter win and remembers it", () => {
    expect(readSettingsVariant("c")).toBe("c");
    expect(storedSettingsVariant()).toBe("c");
    // The address bar does not survive the app's own navigations (login sends
    // the user to /app, which redirects without the query string), so the
    // remembered value has to carry it.
    expect(readSettingsVariant(null)).toBe("c");
  });

  it("keeps different arrangements possible in different tabs", () => {
    readSettingsVariant("b");
    // A tab with an explicit parameter is not dragged back to the stored value.
    expect(readSettingsVariant("a")).toBe("a");
    expect(storedSettingsVariant()).toBe("a");
  });

  it("falls back to the remembered choice for an unknown value", () => {
    readSettingsVariant("c");
    expect(readSettingsVariant("zzz")).toBe("c");
  });

  it("survives a browser that denies storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });

    expect(storedSettingsVariant()).toBeNull();
    // The parameter still works for the URL; nothing throws.
    expect(readSettingsVariant("b")).toBe("b");
    expect(readSettingsVariant(null)).toBe(DEFAULT_SETTINGS_VARIANT);
  });
});
