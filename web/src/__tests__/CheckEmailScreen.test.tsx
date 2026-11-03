import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import CheckEmailScreen from "../routes/CheckEmailScreen";

const { useResendVerificationMock } = vi.hoisted(() => ({
  useResendVerificationMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useResendVerification: () => useResendVerificationMock(),
}));

describe("CheckEmailScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useResendVerificationMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isSuccess: false,
    });
  });

  it("shows the address the link was sent to", () => {
    renderWithProviders(<CheckEmailScreen />, {
      route: "/check-email?email=dan@example.com",
    });

    expect(
      screen.getByRole("heading", { name: "Revisa tu correo" }),
    ).toBeTruthy();
    expect(screen.getByText("dan@example.com")).toBeTruthy();
  });

  it("resends the verification email to the address from the query", () => {
    const mutate = vi.fn();
    useResendVerificationMock.mockReturnValue({
      mutate,
      isPending: false,
      isSuccess: false,
    });
    renderWithProviders(<CheckEmailScreen />, {
      route: "/check-email?email=dan@example.com",
    });

    fireEvent.click(screen.getByRole("button", { name: "Reenviar correo" }));

    expect(mutate).toHaveBeenCalledWith({ email: "dan@example.com" });
  });

  it("confirms the resend once it succeeded", () => {
    useResendVerificationMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isSuccess: true,
    });
    renderWithProviders(<CheckEmailScreen />, {
      route: "/check-email?email=dan@example.com",
    });

    expect(screen.getByRole("status").textContent).toMatch(/correo enviado/i);
  });

  it("disables the resend button while the request is pending", () => {
    useResendVerificationMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
      isSuccess: false,
    });
    renderWithProviders(<CheckEmailScreen />, {
      route: "/check-email?email=dan@example.com",
    });

    const button = screen.getByRole("button", { name: /enviando/i });
    expect(button.hasAttribute("disabled")).toBe(true);
  });

  it("offers the way back to login", () => {
    renderWithProviders(<CheckEmailScreen />, {
      route: "/check-email?email=dan@example.com",
    });

    expect(
      screen.getByRole("link", { name: "Volver a iniciar sesión" }).getAttribute("href"),
    ).toBe("/login");
  });
});
