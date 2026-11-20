import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import LoginScreen from "../routes/LoginScreen";

const { useAppConfigMock } = vi.hoisted(() => ({ useAppConfigMock: vi.fn() }));

vi.mock("../queries/useAppConfig", async () => ({
  ...(await vi.importActual<typeof import("../queries/useAppConfig")>(
    "../queries/useAppConfig",
  )),
  useAppConfig: () => useAppConfigMock(),
}));
vi.mock("../queries/useAuth", () => ({
  useLogin: () => ({ mutateAsync: vi.fn(), isPending: false, error: null }),
  useResendVerification: () => ({ mutate: vi.fn(), isPending: false, isSuccess: false }),
}));

describe("LoginScreen deployment mode (F1 / T1)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the register and recovery links in hosted mode", () => {
    useAppConfigMock.mockReturnValue({ data: { mode: "hosted" }, isError: false });
    renderWithProviders(<LoginScreen />);

    expect(screen.getByRole("link", { name: /register/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /forgot your password/i })).toBeTruthy();
  });

  it("hides the register and recovery links in local mode", () => {
    useAppConfigMock.mockReturnValue({ data: { mode: "local" }, isError: false });
    renderWithProviders(<LoginScreen />);

    expect(screen.queryByRole("link", { name: /register/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /forgot your password/i })).toBeNull();
  });

  it("shows the links when the mode cannot be read (fail open)", () => {
    useAppConfigMock.mockReturnValue({ data: undefined, isError: true });
    renderWithProviders(<LoginScreen />);

    expect(screen.getByRole("link", { name: /register/i })).toBeTruthy();
  });
});
