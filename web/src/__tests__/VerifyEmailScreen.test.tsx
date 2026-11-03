import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import VerifyEmailScreen from "../routes/VerifyEmailScreen";

const { useVerifyEmailMock } = vi.hoisted(() => ({
  useVerifyEmailMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useVerifyEmail: () => useVerifyEmailMock(),
}));

describe("VerifyEmailScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useVerifyEmailMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
      isSuccess: false,
      isError: false,
      error: null,
    });
  });

  it("redeems the token from the query once on mount", () => {
    const mutate = vi.fn();
    useVerifyEmailMock.mockReturnValue({
      mutate,
      isPending: true,
      isSuccess: false,
      isError: false,
      error: null,
    });
    renderWithProviders(<VerifyEmailScreen />, {
      route: "/verify-email?token=abc123",
    });

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith({ token: "abc123" });
  });

  it("shows a loading state while the token is being redeemed", () => {
    renderWithProviders(<VerifyEmailScreen />, {
      route: "/verify-email?token=abc123",
    });

    expect(screen.getByText("Verificando tu correo…")).toBeTruthy();
  });

  it("confirms a verified address and links to login (D10)", () => {
    useVerifyEmailMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isSuccess: true,
      isError: false,
      error: null,
    });
    renderWithProviders(<VerifyEmailScreen />, {
      route: "/verify-email?token=abc123",
    });

    expect(screen.getByRole("heading", { name: "Correo verificado" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Ir a iniciar sesión" }).getAttribute("href"),
    ).toBe("/login");
  });

  it("tells the person the link is invalid or expired on 400", () => {
    useVerifyEmailMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isSuccess: false,
      isError: true,
      error: { status: 400, message: "Invalid or expired token" },
    });
    renderWithProviders(<VerifyEmailScreen />, {
      route: "/verify-email?token=expired",
    });

    expect(
      screen.getByRole("heading", { name: "El enlace no es válido o ya venció" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Ir a iniciar sesión" }).getAttribute("href"),
    ).toBe("/login");
  });

  it("treats a missing token as an invalid link without calling the API", () => {
    const mutate = vi.fn();
    useVerifyEmailMock.mockReturnValue({
      mutate,
      isPending: false,
      isSuccess: false,
      isError: false,
      error: null,
    });
    renderWithProviders(<VerifyEmailScreen />, { route: "/verify-email" });

    expect(
      screen.getByRole("heading", { name: "El enlace no es válido o ya venció" }),
    ).toBeTruthy();
    expect(mutate).not.toHaveBeenCalled();
  });
});
