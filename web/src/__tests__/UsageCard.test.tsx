/* Tests for the monthly consumption card (T4). The `useUsage` query and the
 * settings query are stubbed at their seams; assertions check what the user
 * sees: a month selector, the stored tokens, the executed and saved analyses,
 * and the cost — with "Sin precio conocido" whenever the server could not price
 * the whole month (never a partial sum). */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, within, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { PreferencesProvider } from "../lib/preferences";
import UsageCard from "../components/UsageCard";
import type { Usage } from "../queries/useUsage";

const { usageMock, settingsMock } = vi.hoisted(() => ({
  usageMock: vi.fn(),
  settingsMock: vi.fn(),
}));

vi.mock("../queries/useUsage", () => ({
  useUsage: () => usageMock(),
}));
vi.mock("../queries/useSettings", () => ({
  useSettings: () => settingsMock(),
}));

const TWO_MONTHS: Usage = {
  months: [
    {
      month: "2026-10",
      tokens_in: 1000,
      tokens_out: 500,
      cost_usd: 1.25,
      cost_known: true,
      analyses: 3,
      archives: 1,
    },
    {
      month: "2026-09",
      tokens_in: 200,
      tokens_out: 100,
      cost_usd: null,
      cost_known: false,
      analyses: 1,
      archives: 0,
    },
  ],
};

function renderCard(data: Usage | undefined, isLoading = false) {
  usageMock.mockReturnValue({ data, isLoading, error: null });
  return renderWithProviders(
    <PreferencesProvider>
      <UsageCard />
    </PreferencesProvider>,
  );
}

/** The month selector (one per card). */
function selector() {
  return screen.getByLabelText("Mes") as HTMLSelectElement;
}

/** Switch the visible month through the selector. */
function pickMonth(month: string) {
  fireEvent.change(selector(), { target: { value: month } });
}

beforeEach(() => {
  vi.clearAllMocks();
  settingsMock.mockReturnValue({
    data: { user_id: 1, number_format: "es", currency_symbol: "US$" },
    isLoading: false,
    error: null,
  });
});

describe("UsageCard", () => {
  it("defaults to the newest month and shows its metrics", () => {
    renderCard(TWO_MONTHS);
    expect(selector().value).toBe("2026-10");
    const block = within(screen.getByRole("group", { name: "2026-10" }));
    expect(block.getByText("1.000")).toBeTruthy();
    expect(block.getByText("500")).toBeTruthy();
    expect(block.getByText("3")).toBeTruthy();
    expect(block.getByText("US$ 1,2500")).toBeTruthy();
  });

  it("labels the available months in Spanish for the selector", () => {
    renderCard(TWO_MONTHS);
    const options = within(selector()).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      "Octubre 2026",
      "Septiembre 2026",
    ]);
  });

  it("shows only the chosen month when the user switches", () => {
    renderCard(TWO_MONTHS);
    pickMonth("2026-09");

    const september = within(screen.getByRole("group", { name: "2026-09" }));
    expect(september.getByText("200")).toBeTruthy();
    expect(september.getByText("100")).toBeTruthy();
    // The other month is gone, not stacked below.
    expect(screen.queryByRole("group", { name: "2026-10" })).toBeNull();
    expect(screen.queryByText("1.000")).toBeNull();
  });

  it("says 'Sin precio conocido' instead of a number for an unpriced month", () => {
    renderCard(TWO_MONTHS);
    pickMonth("2026-09");

    const september = within(screen.getByRole("group", { name: "2026-09" }));
    expect(september.getByText("Sin precio conocido")).toBeTruthy();
    // Never a partial sum presented as a total.
    expect(september.queryByText(/US\$/)).toBeNull();
  });

  it("honours the currency preference for a priced month", () => {
    settingsMock.mockReturnValue({
      data: { user_id: 1, number_format: "es", currency_symbol: "none" },
      isLoading: false,
      error: null,
    });
    renderCard(TWO_MONTHS);
    const block = within(screen.getByRole("group", { name: "2026-10" }));
    expect(block.getByText("1,2500")).toBeTruthy();
  });

  it("shows the current empty month as a known zero cost", () => {
    renderCard({
      months: [
        {
          month: "2026-10",
          tokens_in: 0,
          tokens_out: 0,
          cost_usd: 0.0,
          cost_known: true,
          analyses: 0,
          archives: 0,
        },
      ],
    });
    const block = within(screen.getByRole("group", { name: "2026-10" }));
    expect(block.getByText("US$ 0,0000")).toBeTruthy();
    expect(screen.queryByText("Sin precio conocido")).toBeNull();
  });

  it("shows the stored analyses of each month", () => {
    // S2: "tokens, costo y análisis guardados por mes" — the saved analyses
    // (archives) are part of the panel, not only the executed ones.
    renderCard(TWO_MONTHS);
    const block = within(screen.getByRole("group", { name: "2026-10" }));
    expect(block.getByText("Análisis guardados")).toBeTruthy();
    expect(
      block.getByText("Análisis guardados").nextSibling?.textContent,
    ).toBe("1");
  });
});
