import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";

const { useMeMock } = vi.hoisted(() => ({ useMeMock: vi.fn() }));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => ({ data: undefined }),
  useUpdateSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => useMeMock(),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useChangePassword: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
  useCancelAccountDeletion: () => ({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  }),
}));

import AppShell from "../routes/AppShell";

/**
 * The pending-deletion gate (S6/S7/D6). The "no deletion scheduled" direction is
 * already covered by the navigation smoke tests, whose mocked user carries no
 * `pending_deletion_at`.
 */
describe("AppShell pending-deletion gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("blocks the whole shell with the interstitial instead of the app", () => {
    useMeMock.mockReturnValue({
      data: {
        id: 1,
        email: "test@test.com",
        pending_deletion_at: "2099-01-01 00:00:00",
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<AppShell />, { route: "/app/chat", path: "/app/*" });

    expect(
      screen.getByRole("heading", { name: "Tu cuenta se eliminará" }),
    ).toBeTruthy();
    // No sidebar and no chat view: the grace period locks the app (S6).
    expect(screen.queryByText("Datara")).toBeNull();
    expect(screen.queryByRole("link", { name: "Chat" })).toBeNull();
  });
});
