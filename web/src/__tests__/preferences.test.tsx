import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import {
  DEFAULT_PREFERENCES,
  formatCost,
  formatNumber,
  formatTableValue,
  formatTimestamp,
} from "../lib/preferences";
import { formatNumberEs } from "../lib/formatNumbers";
import { formatRelativeTimeEs } from "../lib/relativeTime";
import PreferencesCard from "../components/PreferencesCard";

const DAY_MS = 24 * 60 * 60 * 1000;

const { useSettingsMock, useUpdateSettingsMock, mutateMock } = vi.hoisted(() => ({
  useSettingsMock: vi.fn(),
  useUpdateSettingsMock: vi.fn(),
  mutateMock: vi.fn(),
}));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => useSettingsMock(),
  useUpdateSettings: () => useUpdateSettingsMock(),
}));

describe("preference formatters", () => {
  it("formatNumber supports Spanish and international separators", () => {
    expect(formatNumber(1234567.5, "es")).toBe("1.234.567,5");
    expect(formatNumber(1234567.5, "intl")).toBe("1,234,567.5");
    // Thousands grouping and trailing-zero trimming apply in both formats.
    expect(formatNumber(5020000, "intl")).toBe("5,020,000");
    expect(formatNumber(5.5, "intl")).toBe("5.5");
    // Negative zero and non-finite values stay sign- and dash-stable.
    expect(formatNumber(-0, "intl")).toBe("0");
    expect(formatNumber(-1234.25, "intl")).toBe("-1,234.25");
    expect(formatNumber(NaN, "intl")).toBe("—");
    expect(formatNumber(Infinity, "intl")).toBe("—");
  });

  it("formatTableValue keeps the em dash and string fallback in both formats", () => {
    expect(formatTableValue(null, "intl")).toBe("—");
    expect(formatTableValue(undefined, "intl")).toBe("—");
    expect(formatTableValue(1234.5, "intl")).toBe("1,234.5");
    expect(formatTableValue(1234.5, "es")).toBe("1.234,5");
    expect(formatTableValue("hola", "intl")).toBe("hola");
    expect(formatTableValue(true, "intl")).toBe("true");
  });

  it("formatTimestamp supports relative and absolute dates", () => {
    const iso = new Date(Date.now() - 5 * DAY_MS).toISOString();
    expect(formatTimestamp(iso, "relative")).toBe("hace 5 días");

    // Anchor on a local date so the assertion is timezone-independent.
    const localDate = new Date(2024, 0, 5, 12, 0, 0);
    expect(formatTimestamp(localDate.toISOString(), "absolute")).toBe("05/01/2024");

    expect(formatTimestamp("not-a-date", "absolute")).toBe("—");
  });

  it("formatCost renders each currency symbol, and none is a bare number", () => {
    expect(formatCost(0.125, "US$")).toBe("US$ 0,1250");
    expect(formatCost(0.125, "$")).toBe("$ 0,1250");
    expect(formatCost(0.125, "USD")).toBe("USD 0,1250");
    expect(formatCost(0.125, "none")).toBe("0,1250");
  });

  it("DEFAULT_PREFERENCES reproduces the pre-preference rendering exactly", () => {
    expect(DEFAULT_PREFERENCES).toEqual({
      numberFormat: "es",
      dateFormat: "relative",
      currencySymbol: "US$",
      openBehavior: "new_session",
    });

    const iso = new Date(Date.now() - 5 * DAY_MS).toISOString();
    expect(formatNumber(1234.5, DEFAULT_PREFERENCES.numberFormat)).toBe(
      formatNumberEs(1234.5),
    );
    expect(formatTableValue(1234.5, DEFAULT_PREFERENCES.numberFormat)).toBe(
      "1.234,5",
    );
    expect(formatTimestamp(iso, DEFAULT_PREFERENCES.dateFormat)).toBe(
      formatRelativeTimeEs(iso),
    );
    expect(formatCost(0.125, DEFAULT_PREFERENCES.currencySymbol)).toBe(
      "US$ 0,1250",
    );
  });
});

describe("PreferencesCard", () => {
  beforeEach(() => {
    useSettingsMock.mockReset();
    mutateMock.mockReset();
    useUpdateSettingsMock.mockReset();
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        number_format: "intl",
        date_format: "absolute",
        currency_symbol: "$",
        open_behavior: "last_session",
      },
      isLoading: false,
      error: null,
    });
    useUpdateSettingsMock.mockReturnValue({ mutate: mutateMock, isPending: false });
    // Mirror the api call resolving successfully.
    mutateMock.mockImplementation(
      (_data: unknown, options?: { onSuccess?: () => void }) =>
        options?.onSuccess?.(),
    );
  });

  it("renders the stored values in the four controls", () => {
    renderWithProviders(<PreferencesCard />);

    expect((screen.getByLabelText("Formato de números") as HTMLSelectElement).value).toBe(
      "intl",
    );
    expect((screen.getByLabelText("Formato de fechas") as HTMLSelectElement).value).toBe(
      "absolute",
    );
    expect(
      (screen.getByLabelText("Símbolo de moneda") as HTMLSelectElement).value,
    ).toBe("$");
    expect(
      (screen.getByLabelText("Comportamiento al abrir") as HTMLSelectElement).value,
    ).toBe("last_session");
  });

  it("saves a change and shows the confirmation", () => {
    renderWithProviders(<PreferencesCard />);

    fireEvent.change(screen.getByLabelText("Formato de números"), {
      target: { value: "es" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar preferencias" }));

    expect(mutateMock).toHaveBeenCalledWith(
      {
        number_format: "es",
        date_format: "absolute",
        currency_symbol: "$",
        open_behavior: "last_session",
      },
      expect.anything(),
    );
    expect(screen.getByRole("status").textContent).toBe("Preferencias guardadas");
  });

  it("restores every default with the reset button", () => {
    renderWithProviders(<PreferencesCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Restablecer valores por defecto" }),
    );

    expect(mutateMock).toHaveBeenCalledWith(
      {
        number_format: "es",
        date_format: "relative",
        currency_symbol: "US$",
        open_behavior: "new_session",
      },
      expect.anything(),
    );
    expect((screen.getByLabelText("Formato de números") as HTMLSelectElement).value).toBe(
      "es",
    );
    expect((screen.getByLabelText("Formato de fechas") as HTMLSelectElement).value).toBe(
      "relative",
    );
    expect(screen.getByRole("status").textContent).toBe("Preferencias restablecidas");
  });

  it("falls back to the defaults while settings are loading", () => {
    useSettingsMock.mockReturnValue({ data: undefined, isLoading: true, error: null });
    renderWithProviders(<PreferencesCard />);

    expect((screen.getByLabelText("Formato de números") as HTMLSelectElement).value).toBe(
      "es",
    );
    expect((screen.getByLabelText("Formato de fechas") as HTMLSelectElement).value).toBe(
      "relative",
    );
    expect(
      (screen.getByLabelText("Símbolo de moneda") as HTMLSelectElement).value,
    ).toBe("US$");
    expect(
      (screen.getByLabelText("Comportamiento al abrir") as HTMLSelectElement).value,
    ).toBe("new_session");
  });
});
