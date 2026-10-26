/* Regression tests for the display preferences (T7a), driven through the real
 * components inside `PreferencesProvider` -- the UI path, not the pure
 * formatters. A settings payload is fed via the `useSettings` query hook (the
 * same seam the app uses); nothing else hides the preference flow.
 *
 * Each preference asserts its observable rendering: the number that is painted,
 * the cost label that is painted, and the timestamp that is painted. The
 * default cases pin the pre-preference output, so adopting preferences cannot
 * silently change what the app already showed.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { PreferencesProvider } from "../lib/preferences";
import DataFrameTable from "../components/DataFrameTable";
import ChatMessage from "../components/ChatMessage";
import ArchiveList from "../routes/ArchiveList";
import type { Archive } from "../queries/useArchives";

const {
  settingsMock,
  useArchivesMock,
  useArchiveDetailMock,
  useDeleteArchiveMock,
  useRenameArchiveMock,
  apiGetMock,
  downloadTextFileMock,
} = vi.hoisted(() => ({
  settingsMock: vi.fn(),
  useArchivesMock: vi.fn(),
  useArchiveDetailMock: vi.fn(),
  useDeleteArchiveMock: vi.fn(),
  useRenameArchiveMock: vi.fn(),
  apiGetMock: vi.fn(),
  downloadTextFileMock: vi.fn(),
}));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => settingsMock(),
  useUpdateSettings: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../queries/useArchives", () => ({
  useArchives: (...a: unknown[]) => useArchivesMock(...a),
  useArchiveDetail: (id: number | null) => useArchiveDetailMock(id),
  useDeleteArchive: () => useDeleteArchiveMock(),
  useRenameArchive: () => useRenameArchiveMock(),
}));
vi.mock("../lib/api", () => ({
  api: {
    get: (...a: unknown[]) => apiGetMock(...a),
    patch: vi.fn(),
    delete: vi.fn(),
    post: vi.fn(),
  },
}));
vi.mock("../lib/archiveMarkdown", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/archiveMarkdown")>();
  return {
    ...actual,
    downloadTextFile: (...a: unknown[]) => downloadTextFileMock(...a),
  };
});

const DAY_MS = 24 * 60 * 60 * 1000;

function makeArchive(overrides: Partial<Archive> = {}): Archive {
  return {
    id: 1,
    name: "Margen por región",
    chat_session: "ses_1",
    created_at: new Date(2024, 0, 5, 12, 0, 0).toISOString(),
    files: ["ventas_q3.csv"],
    row_count: 1000,
    column_count: 2,
    ...overrides,
  };
}

function mockList(data: Archive[]) {
  useArchivesMock.mockReturnValue({
    data: { pages: [data] },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    hasNextPage: false,
    fetchNextPage: vi.fn(),
    isFetchingNextPage: false,
  });
  useArchiveDetailMock.mockReturnValue({ data: undefined, isLoading: false });
  useDeleteArchiveMock.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useRenameArchiveMock.mockReturnValue({ mutate: vi.fn(), isPending: false });
}

beforeEach(() => {
  settingsMock.mockReset();
  settingsMock.mockReturnValue({ data: undefined, isLoading: true, error: null });
});

describe("DataFrameTable renders through the preferences provider", () => {
  it("intl settings render international separators in real cells", () => {
    settingsMock.mockReturnValue({
      data: { user_id: 1, number_format: "intl" },
      isLoading: false,
      error: null,
    });
    renderWithProviders(
      <PreferencesProvider>
        <DataFrameTable columns={["valor"]} rows={[[1234.56]]} totalRows={12345} />
      </PreferencesProvider>,
    );
    expect(screen.getByText("1,234.56")).toBeTruthy();
    expect(
      screen.getByText(/Mostrando las primeras 1 de 12,345 filas\./),
    ).toBeTruthy();
  });

  it("es settings keep the Spanish convention", () => {
    settingsMock.mockReturnValue({
      data: { user_id: 1, number_format: "es" },
      isLoading: false,
      error: null,
    });
    renderWithProviders(
      <PreferencesProvider>
        <DataFrameTable columns={["valor"]} rows={[[1234.56]]} />
      </PreferencesProvider>,
    );
    expect(screen.getByText("1.234,56")).toBeTruthy();
  });

  it("defaults (settings still loading) reproduce today's Spanish output", () => {
    // beforeEach leaves the query in its loading state: no preference is known,
    // so the provider must serve the defaults and change nothing.
    renderWithProviders(
      <PreferencesProvider>
        <DataFrameTable columns={["valor"]} rows={[[1234.56]]} />
      </PreferencesProvider>,
    );
    expect(screen.getByText("1.234,56")).toBeTruthy();
  });
});

describe("ChatMessage cost line honors currency_symbol", () => {
  const renderCost = () =>
    renderWithProviders(
      <PreferencesProvider>
        <ChatMessage role="assistant" content="x" tokensIn={100} tokensOut={50} costUsd={0.125} />
      </PreferencesProvider>,
    );

  it("default settings render US$ 0,1250 (pre-change output)", () => {
    settingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: true,
        provider_type: "openrouter",
        default_model: "gpt-4o",
      },
      isLoading: false,
      error: null,
    });
    renderCost();
    expect(screen.getByText(/US\$ 0,1250/)).toBeTruthy();
  });

  it("currency_symbol none renders the bare number", () => {
    settingsMock.mockReturnValue({
      data: { user_id: 1, currency_symbol: "none" },
      isLoading: false,
      error: null,
    });
    renderCost();
    expect(screen.getByText(/0,1250/)).toBeTruthy();
    expect(screen.queryByText(/US\$/)).toBeNull();
    expect(screen.queryByText(/\$/)).toBeNull();
  });
});

describe("ArchiveList timestamp honors date_format", () => {
  it("absolute renders dd/mm/aaaa in the real card", () => {
    settingsMock.mockReturnValue({
      data: { user_id: 1, date_format: "absolute" },
      isLoading: false,
      error: null,
    });
    mockList([makeArchive()]);
    renderWithProviders(
      <PreferencesProvider>
        <ArchiveList />
      </PreferencesProvider>,
    );
    expect(screen.getByText("05/01/2024")).toBeTruthy();
    expect(screen.queryByText(/hace \d+ días/)).toBeNull();
  });

  it("default settings keep the relative phrasing (pre-change output)", () => {
    settingsMock.mockReturnValue({
      data: { user_id: 1 },
      isLoading: false,
      error: null,
    });
    const iso = new Date(Date.now() - 5 * DAY_MS).toISOString();
    mockList([makeArchive({ created_at: iso })]);
    renderWithProviders(
      <PreferencesProvider>
        <ArchiveList />
      </PreferencesProvider>,
    );
    expect(screen.getByText("hace 5 días")).toBeTruthy();
  });
});
