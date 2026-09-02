import { describe, it, expect, vi } from "vitest";
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
  it("renders Chat view at /app/chat", async () => {
    renderWithProviders(<AppShell />, { route: "/app/chat" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(screen.getByText("Chat")).toBeTruthy();
  });

  it("renders Files view at /app/files", async () => {
    renderWithProviders(<AppShell />, { route: "/app/files" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(screen.getByText("Files")).toBeTruthy();
  });

  it("renders Settings view at /app/settings", async () => {
    renderWithProviders(<AppShell />, { route: "/app/settings" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(screen.getByText("Settings")).toBeTruthy();
  });

  it("renders Archives view at /app/archives", async () => {
    renderWithProviders(<AppShell />, { route: "/app/archives" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(screen.getByText("Archives")).toBeTruthy();
  });

  it("renders sidebar navigation links", () => {
    renderWithProviders(<AppShell />, { route: "/app/chat" });
    expect(screen.getByText("Datara")).toBeTruthy();
    expect(screen.getByText("test@test.com")).toBeTruthy();
  });
});