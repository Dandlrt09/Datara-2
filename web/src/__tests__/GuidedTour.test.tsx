/* Guided first-boot tour (F4 / T4, S2, S3, D5).
 *
 * The behaviours pinned here are the ones the frente promised:
 *   - it shows on the first entry of a profile that never saw it (S3 flag false),
 *   - it never shows for a profile whose flag is true (S3),
 *   - it never shows while the lock step is pending (it sits behind that gate),
 *   - it walks the sidebar tabs: every step opens its own section through the
 *     shell's `onGoTo` and points at that sidebar entry, and the closing step
 *     returns to Ajustes to configure the API key (S2),
 *   - skip and the final step both mark it through the API and close it (S2/S3),
 *   - a failed mark closes it for THIS session anyway and does not fake the flag (D5),
 *   - it reopens from the chat empty state, the slot the old wizard used (D5).
 *
 * The component, the AppShell gate and the ChatView reopen control are the real
 * ones; every query the shell reads over the network is mocked, and `fetch` is
 * stubbed so only the tour's own mutation can reach it.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  cleanup,
  act,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// Lazy views are stubbed so nothing but the shell and ChatView runs.
vi.mock("../routes/FilesView", () => ({ default: () => <div>Files</div> }));
vi.mock("../routes/SettingsView", () => ({
  default: () => <div data-testid="settings-view">Settings</div>,
}));
vi.mock("../routes/ArchiveList", () => ({ default: () => <div>Archives</div> }));
vi.mock("../routes/LockStepScreen", () => ({ default: () => <div>Lock step</div> }));

const { useMeMock, useLocalProfileStatusMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useLocalProfileStatusMock: vi.fn(),
}));

// The real module is kept: `useMarkTutorialSeen` must stay the production hook
// and hit the stubbed fetch, so the mark is proven at the HTTP boundary.
vi.mock("../queries/useAuth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../queries/useAuth")>();
  return {
    ...actual,
    useMe: () => useMeMock(),
    useLocalProfileStatus: () => useLocalProfileStatusMock(),
  };
});

vi.mock("../queries/useAppConfig", () => ({
  emailFlowsEnabled: () => false,
  useAppConfig: () => ({ data: { mode: "local" }, isError: false }),
}));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => ({ data: undefined, isLoading: true }),
}));

const {
  useSessionsMock,
  useCreateSessionMock,
  useDeleteSessionMock,
  useRenameSessionMock,
  useMessagesMock,
  useFilesGlobalMock,
  useUploadFileMock,
  useCreateArchiveMock,
} = vi.hoisted(() => ({
  useSessionsMock: vi.fn(),
  useCreateSessionMock: vi.fn(),
  useDeleteSessionMock: vi.fn(),
  useRenameSessionMock: vi.fn(),
  useMessagesMock: vi.fn(),
  useFilesGlobalMock: vi.fn(),
  useUploadFileMock: vi.fn(),
  useCreateArchiveMock: vi.fn(),
}));

vi.mock("../queries/useSessions", () => ({
  useSessions: () => useSessionsMock(),
  useCreateSession: () => useCreateSessionMock(),
  useDeleteSession: () => useDeleteSessionMock(),
  useRenameSession: () => useRenameSessionMock(),
}));

vi.mock("../queries/useMessages", () => ({ useMessages: () => useMessagesMock() }));

vi.mock("../queries/useFiles", () => ({
  useFilesGlobal: () => useFilesGlobalMock(),
  useUploadFile: () => useUploadFileMock(),
  // ChatView catches `instanceof UploadError`; a plain class keeps that true.
  UploadError: class UploadError extends Error {},
}));

vi.mock("../queries/useArchives", () => ({
  useCreateArchive: () => useCreateArchiveMock(),
}));

vi.mock("../lib/useSessionEvents", () => ({ useSessionEvents: () => {} }));
vi.mock("../lib/sse", () => ({ streamChat: vi.fn() }));

import AppShell from "../routes/AppShell";
import { GuidedTour, useGuidedTourStore } from "../components/GuidedTour";
import { useChatStore } from "../stores/useChatStore";

const TOUR_DIALOG = { name: /recorrido guiado/i };

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

/** One `useMe` payload for a hosted account with the given tour flag. */
const me = (tutorialSeen: boolean, overrides: Record<string, unknown> = {}) => ({
  data: {
    id: 1,
    email: "analista@datara.test",
    name: null,
    pending_deletion_at: null,
    tutorial_seen: tutorialSeen,
    ...overrides,
  },
  isLoading: false,
  error: null,
});

/** `fetch` answer for the mark route: 204 No Content, like the server. */
const answer204 = () => ({
  ok: true,
  status: 204,
  json: async () => undefined,
  text: async () => "",
});

/** `fetch` answer for a refused mark. */
const answer500 = () => ({
  ok: false,
  status: 500,
  json: async () => ({ detail: "boom" }),
  text: async () => "boom",
});

let fetchMock: ReturnType<typeof vi.fn>;

const renderShell = (queryClient: QueryClient = makeQueryClient()) => ({
  queryClient,
  ...render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/app/chat"]}>
        <Routes>
          <Route path="/app/*" element={<AppShell />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  ),
});

const renderTour = (onClose = vi.fn(), onGoTo = vi.fn()) => {
  const queryClient = makeQueryClient();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <GuidedTour onClose={onClose} onGoTo={onGoTo} />
    </QueryClientProvider>,
  );
  return { ...view, onClose, onGoTo, queryClient };
};

/** Press "Siguiente" *times* times, exactly like an analyst walking the tour. */
const advance = (times: number) => {
  for (let i = 0; i < times; i += 1) {
    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
  }
};

beforeEach(() => {
  vi.clearAllMocks();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  // Isolation only, never an assertion: the tour store is a module singleton
  // and each test starts from "never offered in this session".
  useGuidedTourStore.setState({ open: false, firstEntryClosed: false });

  useChatStore.setState({ isStreaming: false, streamingText: "", pendingArtifacts: null });

  useLocalProfileStatusMock.mockReturnValue({
    data: { exists: true, hosted_accounts: false, locked: false, lock_step_pending: false },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  });
  useSessionsMock.mockReturnValue({
    data: [],
    isLoading: false,
    isSuccess: true,
    isError: false,
    refetch: vi.fn(),
  });
  useFilesGlobalMock.mockReturnValue({
    data: [],
    isLoading: false,
    isSuccess: true,
    isError: false,
    hasMore: false,
    loadMore: vi.fn(),
    isLoadingMore: false,
  });
  useMessagesMock.mockReturnValue({
    messages: [],
    hasMore: false,
    isLoadingOlder: false,
    loadOlderError: null,
    error: null,
    refetch: vi.fn(),
    loadOlder: vi.fn().mockResolvedValue(undefined),
  });
  useCreateSessionMock.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ id: "ses-new", title: "New" }),
    isPending: false,
  });
  useDeleteSessionMock.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useRenameSessionMock.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useUploadFileMock.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ id: 1, filename: "a.csv" }),
    isPending: false,
  });
  useCreateArchiveMock.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ id: 1, name: "análisis" }),
    isPending: false,
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("guided tour gate", () => {
  it("shows on the first entry of a profile that never saw it", async () => {
    useMeMock.mockReturnValue(me(false));

    renderShell();

    expect(await screen.findByRole("dialog", TOUR_DIALOG)).toBeTruthy();
    expect(screen.getByText("Paso 1 de 6")).toBeTruthy();
    // The step points at the sidebar entry it opens, and the shell's navigator
    // is wired in: the real Ajustes section shows behind the card.
    expect(document.querySelector('[data-tour="nav-settings"]')).toBeTruthy();
    expect(await screen.findByTestId("settings-view")).toBeTruthy();
  });

  it("never shows for a profile whose flag is already true", async () => {
    useMeMock.mockReturnValue(me(true));

    renderShell();

    // Wait for the shell (and the lazily loaded ChatView) to be on screen, so
    // the absence below is a settled absence and not a pre-render one. What the
    // wait covers is a dynamic import, and under a full parallel suite that
    // chunk can take longer than the 1s default, so it gets a generous timeout
    // instead of a flaky one.
    expect(
      await screen.findByText("+ New Chat", undefined, { timeout: 5000 }),
    ).toBeTruthy();
    expect(screen.queryByRole("dialog", TOUR_DIALOG)).toBeNull();
  });

  it("does not show while the lock step is pending", async () => {
    useMeMock.mockReturnValue(me(false, { email: null }));
    useLocalProfileStatusMock.mockReturnValue({
      data: { exists: true, hosted_accounts: false, locked: false, lock_step_pending: true },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderShell();

    expect(await screen.findByText("Lock step")).toBeTruthy();
    expect(screen.queryByRole("dialog", TOUR_DIALOG)).toBeNull();
  });

  it("reopens from the chat empty state, the slot the old wizard used", async () => {
    useMeMock.mockReturnValue(me(true));

    renderShell();

    // Same lazily loaded empty state as above: wait past the chunk import.
    const reopen = await screen.findByRole(
      "button",
      { name: "Ver el recorrido guiado" },
      { timeout: 5000 },
    );
    expect(screen.queryByRole("dialog", TOUR_DIALOG)).toBeNull();

    fireEvent.click(reopen);

    expect(await screen.findByRole("dialog", TOUR_DIALOG)).toBeTruthy();
    expect(screen.getByText("Paso 1 de 6")).toBeTruthy();
  });
});

/* S2 / the walk navigates the tabs. Each step opens its own section through the
 * `onGoTo` prop the shell hands in (a real `useNavigate`), and the closing step
 * returns the analyst to Ajustes to configure the API key. Navigation is a prop,
 * never an import: the component stays renderable bare, as these specs do. */
describe("guided tour navigation", () => {
  it("opens Ajustes on the first step, so the section shows behind the card", () => {
    const { onGoTo } = renderTour();

    expect(screen.getByText("Paso 1 de 6")).toBeTruthy();
    expect(onGoTo).toHaveBeenCalledTimes(1);
    expect(onGoTo).toHaveBeenLastCalledWith("/app/settings");
  });

  it("asks for each next tab in order and returns to Ajustes to close", () => {
    fetchMock.mockResolvedValue(answer204());
    const { onClose, onGoTo } = renderTour();

    advance(5);
    expect(screen.getByText("Paso 6 de 6")).toBeTruthy();

    // One navigation per step change: Ajustes, Chat, Files, Archives, Perfil
    // and the closing step back in Ajustes.
    expect(onGoTo.mock.calls.map(([route]) => route)).toEqual([
      "/app/settings",
      "/app/chat",
      "/app/files",
      "/app/archives",
      "/app/profile",
      "/app/settings",
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Terminar" }));
    expect(onGoTo).toHaveBeenLastCalledWith("/app/settings");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

/* S2 / the reachable-card rule. A step whose anchor is a full-height column
 * (the sidebar) has no room above or below it, and the old "above" placement
 * pushed the whole card past the top edge: the analyst saw a 12px strip and
 * could neither read the step nor press its buttons. The card must always land
 * inside the viewport. */
describe("guided tour tooltip placement", () => {
  it("keeps the card inside the viewport for a full-height anchor", async () => {
    const anchor = document.createElement("nav");
    anchor.setAttribute("data-tour", "nav-settings");
    document.body.appendChild(anchor);
    vi.spyOn(anchor, "getBoundingClientRect").mockReturnValue({
      top: 0,
      bottom: window.innerHeight,
      left: 0,
      right: 220,
      width: 220,
      height: window.innerHeight,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);

    renderTour();

    const card = await screen.findByRole("dialog", TOUR_DIALOG);
    const top = Number.parseInt(String(card.style.top), 10);
    // Visible from the top edge down, and its bottom edge still on screen.
    expect(top).toBeGreaterThanOrEqual(12);
    expect(top + 210).toBeLessThanOrEqual(window.innerHeight);
    // Placed beside the column, so no off-screen vertical transform.
    expect(card.style.transform).toBe("");

    anchor.remove();
  });
});

describe("guided tour completion", () => {
  it("skip marks it seen through the API and closes the tour", async () => {
    fetchMock.mockResolvedValue(answer204());
    const { onClose } = renderTour();

    fireEvent.click(screen.getByRole("button", { name: "Saltar" }));

    // Closed right away: the analyst is never held behind the tour.
    expect(onClose).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/tutorial-seen");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "POST",
      credentials: "include",
    });
  });

  it("the final step finishes the tour and marks it seen", async () => {
    fetchMock.mockResolvedValue(answer204());
    const { onClose } = renderTour();

    advance(5);
    expect(screen.getByText("Paso 6 de 6")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Terminar" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/tutorial-seen");
  });

  it("escape closes it and marks it seen like a skip", async () => {
    fetchMock.mockResolvedValue(answer204());
    const { onClose } = renderTour();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("a failed mark still closes it for this session and never fakes the flag", async () => {
    fetchMock.mockResolvedValue(answer500());
    const { onClose, queryClient } = renderTour();
    const cachedMe = {
      id: 1,
      email: "analista@datara.test",
      name: null,
      pending_deletion_at: null,
      tutorial_seen: false,
    };
    queryClient.setQueryData(["auth", "me"], cachedMe);

    fireEvent.click(screen.getByRole("button", { name: "Saltar" }));

    // No nagging: the refusal closes the tour for this session too.
    expect(onClose).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      await Promise.resolve();
    });

    // The stored flag is untouched: the tour comes back on a later launch.
    expect(queryClient.getQueryData(["auth", "me"])).toEqual(cachedMe);
  });
});
