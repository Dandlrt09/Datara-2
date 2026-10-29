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
vi.mock("../routes/ProfileView", () => ({
  default: () => <div data-testid="profile-view"><h1>Perfil</h1></div>,
}));
const { useSettingsMock } = vi.hoisted(() => ({ useSettingsMock: vi.fn() }));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => useSettingsMock(),
  useUpdateSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const { useMeMock } = vi.hoisted(() => ({ useMeMock: vi.fn() }));

vi.mock("../queries/useAuth", () => ({
  useMe: () => useMeMock(),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useChangePassword: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
  useUpdateName: () => ({ mutate: vi.fn(), isPending: false }),
}));

// Import AppShell AFTER mocks are hoisted
import AppShell from "../routes/AppShell";

describe("Navigation smoke (R-TestWall-3)", () => {
  beforeEach(() => {
    useMeMock.mockReturnValue({
      data: { id: 1, email: "test@test.com", name: null },
      isLoading: false,
      error: null,
    });
  });

  // T1/D6: the sidebar and Perfil share one resolver, so a chosen name shows up
  // in the user block instead of the email local part.
  it("shows the chosen name in the sidebar user block", () => {
    useMeMock.mockReturnValue({
      data: { id: 1, email: "test@test.com", name: "Daniel" },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });

    expect(screen.getByText("Daniel")).toBeTruthy();
    expect(screen.queryByText("test")).toBeNull();
  });

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

  it("renders Profile view at /app/profile", async () => {
    renderWithProviders(<AppShell />, { route: "/app/profile", path: "/app/*" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(await screen.findByTestId("profile-view")).toBeTruthy();
  });

  it("renders sidebar navigation links", () => {
    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(screen.getByText("test@test.com")).toBeTruthy();
  });

  it("links the sidebar user block to the profile", () => {
    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });
    const link = screen.getByRole("link", { name: /test@test\.com/ });
    expect(link.getAttribute("href")).toBe("/app/profile");
  });
});

describe("Ajustes — una sola pantalla y el aterrizaje de primer uso", () => {
  beforeEach(() => {
    useSettingsMock.mockReset();
    useSettingsMock.mockReturnValue({
      data: { user_id: 1, has_api_key: false, provider_type: null, default_model: null },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("sends the old /app/setup URL back to the single settings screen", async () => {
    renderWithProviders(<AppShell />, { route: "/app/setup", path: "/app/*" });

    expect(await screen.findByTestId("settings-view")).toBeTruthy();
  });

  it("lands on Ajustes when nothing is configured", async () => {
    renderWithProviders(<AppShell />, { route: "/app", path: "/app/*" });

    // The guided flow is Ajustes' own default mode there (S5).
    expect(await screen.findByTestId("settings-view")).toBeTruthy();
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
    renderWithProviders(<AppShell />, { route: "/app", path: "/app/*" });

    expect(await screen.findByTestId("chat-view")).toBeTruthy();
  });
});