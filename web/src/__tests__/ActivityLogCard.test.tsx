/* Tests for the personal activity log card (T6). The `useActivity` query and
 * the settings query are stubbed at their seams; assertions check what the
 * user sees: the month totals, the mixed feed, the empty state and the
 * "computed from what exists today" notice (S6). */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { PreferencesProvider } from "../lib/preferences";
import ActivityLogCard from "../components/ActivityLogCard";
import type { Activity } from "../queries/useActivity";

const { activityMock, settingsMock } = vi.hoisted(() => ({
  activityMock: vi.fn(),
  settingsMock: vi.fn(),
}));

vi.mock("../queries/useActivity", () => ({
  useActivity: () => activityMock(),
}));
vi.mock("../queries/useSettings", () => ({
  useSettings: () => settingsMock(),
}));

const FULL: Activity = {
  events: [
    { kind: "archive", title: "Informe Q1", at: "2025-03-03 09:00:00" },
    { kind: "file", title: "ventas.csv", at: "2025-03-02 09:00:00" },
    { kind: "chat", title: "Revisión de ventas", at: "2025-03-01 09:00:00" },
  ],
  month: { chats: 3, analyses: 7, files: 2, rows: 1500, archives: 1 },
};

function renderCard(data: Activity | undefined, isLoading = false) {
  activityMock.mockReturnValue({ data, isLoading, error: null });
  return renderWithProviders(
    <PreferencesProvider>
      <ActivityLogCard />
    </PreferencesProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  settingsMock.mockReturnValue({
    data: { user_id: 1, date_format: "absolute", number_format: "es" },
    isLoading: false,
    error: null,
  });
});

describe("ActivityLogCard", () => {
  it("shows the month totals with their labels", () => {
    renderCard(FULL);
    expect(screen.getByText("Chats iniciados").nextSibling?.textContent).toBe("3");
    expect(screen.getByText("Análisis ejecutados").nextSibling?.textContent).toBe("7");
    expect(screen.getByText("Archivos subidos").nextSibling?.textContent).toBe("2");
    expect(screen.getByText("Filas procesadas").nextSibling?.textContent).toMatch(/1.?500/);
    expect(screen.getByText("Análisis guardados").nextSibling?.textContent).toBe("1");
  });

  it("lists the feed events with a label per kind", () => {
    renderCard(FULL);
    expect(screen.getByText("Informe Q1")).toBeTruthy();
    expect(screen.getByText("ventas.csv")).toBeTruthy();
    expect(screen.getByText("Revisión de ventas")).toBeTruthy();
    expect(screen.getByText("Análisis guardado")).toBeTruthy();
    expect(screen.getByText("Archivo subido")).toBeTruthy();
    expect(screen.getByText("Chat creado")).toBeTruthy();
  });

  it("shows an empty state when there is no activity", () => {
    renderCard({
      events: [],
      month: { chats: 0, analyses: 0, files: 0, rows: 0, archives: 0 },
    });
    expect(screen.getByText("Todavía no hay actividad.")).toBeTruthy();
  });

  it("warns that it reflects only what exists today", () => {
    renderCard(FULL);
    expect(screen.getByText(/refleja lo que existe hoy/i)).toBeTruthy();
  });
});
