import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";

// Mock ALL route components at once — vitest hoists these so they
// replace the lazy import before any React code runs
vi.mock("../routes/ChatView", () => ({
  default: () => <div data-testid="chat-view"><h1>Chat</h1></div>,
}));
vi.mock("../routes/FilesView", () => ({
  default: () => <div data-testid="files-view"><h1>Files</h1></div>,
}));
vi.mock("../routes/SettingsView", () => ({
  default: () => <div data-testid="settings-view"><h1>Settings</h1></div>,
}));
vi.mock("../routes/ArchiveList", () => ({
  default: () => <div data-testid="archives-view"><h1>Archives</h1></div>,
}));
vi.mock("../routes/Setup", () => ({
  default: () => <div data-testid="setup-view"><h1>Setup</h1></div>,
}));

const { useSettingsMock } = vi.hoisted(() => ({ useSettingsMock: vi.fn() }));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => useSettingsMock(),
  useUpdateSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => ({
    data: { id: 1, email: "test@test.com" },
    isLoading: false,
    error: null,
  }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// Import AppShell AFTER mocks are hoisted
import AppShell from "../routes/AppShell";

describe("Navigation smoke (R-TestWall-3)", () => {
  // `path: "/app/*"` is load-bearing: AppShell's own <Routes> hang off the
  // /app/* parent in App.tsx, and its child paths only resolve against it.
  // Rendered bare at "/app/archives", every child route misses and the 404
  // catches it — which the old assertions could not see, because they only
  // checked the sidebar labels (present on every page).
  it("renders Chat view at /app/chat", async () => {
    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });
    expect(screen.getByText("Datara")).toBeTruthy();
    // The route components are lazy: the assertion has to wait for the
    // Suspense boundary to resolve, not read the fallback.
    expect(await screen.findByTestId("chat-view")).toBeTruthy();
    expect(screen.queryByText("404")).toBeNull();
  });

  it("renders Files view at /app/files", async () => {
    renderWithProviders(<AppShell />, { route: "/app/files", path: "/app/*" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(await screen.findByTestId("files-view")).toBeTruthy();
  });

  it("renders Settings view at /app/settings", async () => {
    renderWithProviders(<AppShell />, { route: "/app/settings", path: "/app/*" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(await screen.findByTestId("settings-view")).toBeTruthy();
  });

  it("renders Archives view at /app/archives", async () => {
    renderWithProviders(<AppShell />, { route: "/app/archives", path: "/app/*" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(await screen.findByTestId("archives-view")).toBeTruthy();
  });

  it("renders sidebar navigation links", () => {
    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(screen.getByText("test@test.com")).toBeTruthy();
  });
});

describe("Settings fusion — arrangement variants and first-use landing", () => {
  beforeEach(() => {
    useSettingsMock.mockReset();
    useSettingsMock.mockReturnValue({
      data: { user_id: 1, has_api_key: false, provider_type: null, default_model: null },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("variant A sends /app/setup back to the one settings screen", async () => {
    renderWithProviders(<AppShell />, { route: "/app/setup?variante=a", path: "/app/*" });

    expect(await screen.findByTestId("settings-view")).toBeTruthy();
    expect(screen.queryByTestId("setup-view")).toBeNull();
  });

  it("variant B sends /app/setup back to the one settings screen", async () => {
    renderWithProviders(<AppShell />, { route: "/app/setup?variante=b", path: "/app/*" });

    expect(await screen.findByTestId("settings-view")).toBeTruthy();
    expect(screen.queryByTestId("setup-view")).toBeNull();
  });

  it("variant C keeps the guided route reachable", async () => {
    renderWithProviders(<AppShell />, { route: "/app/setup?variante=c", path: "/app/*" });

    expect(await screen.findByTestId("setup-view")).toBeTruthy();
  });

  it("lands on the guided flow when nothing is configured", async () => {
    renderWithProviders(<AppShell />, { route: "/app?variante=a", path: "/app/*" });

    // Variant A carries the guided flow inside the settings screen.
    expect(await screen.findByTestId("settings-view")).toBeTruthy();
  });

  it("lands on the guided route of variant C when nothing is configured", async () => {
    renderWithProviders(<AppShell />, { route: "/app?variante=c", path: "/app/*" });

    expect(await screen.findByTestId("setup-view")).toBeTruthy();
  });

  it("lands on chat once a provider and a model are stored", async () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: true,
        provider_type: "openrouter",
        default_model: "gpt-4o",
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    renderWithProviders(<AppShell />, { route: "/app?variante=a", path: "/app/*" });

    expect(await screen.findByTestId("chat-view")).toBeTruthy();
  });
});