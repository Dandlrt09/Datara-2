import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderWithProviders } from "./test-utils";
import LoginScreen from "../routes/LoginScreen";
import { DELETION_SCHEDULED_NOTICE } from "../components/DeleteAccountDialog";

const { useLoginMock, useResendVerificationMock } = vi.hoisted(() => ({
  useLoginMock: vi.fn(),
  useResendVerificationMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useLogin: () => useLoginMock(),
  useResendVerification: () => useResendVerificationMock(),
}));

describe("LoginScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useLoginMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    useResendVerificationMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isSuccess: false,
    });
  });

  it("renders the form", () => {
    renderWithProviders(<LoginScreen />);
    expect(screen.getByRole("heading", { name: /log in/i })).toBeTruthy();
    expect(screen.getByPlaceholderText("Email")).toBeTruthy();
    expect(screen.getByPlaceholderText("Password")).toBeTruthy();
    expect(screen.getByRole("button", { name: /log in/i })).toBeTruthy();
  });

  it("shows error message on login failure", () => {
    useLoginMock.mockReturnValue({
      mutateAsync: vi.fn().mockRejectedValue(new Error("Invalid credentials")),
      isPending: false,
      error: { status: 401, message: "Invalid credentials" },
    });
    renderWithProviders(<LoginScreen />);
    expect(screen.getByText("Invalid credentials")).toBeTruthy();
  });

  it("shows the deletion notice carried in navigation state (S5)", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter
          initialEntries={[
            { pathname: "/login", state: { notice: DELETION_SCHEDULED_NOTICE } },
          ]}
        >
          <LoginScreen />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("status").textContent).toBe(DELETION_SCHEDULED_NOTICE);
  });

  it("shows no notice when navigation state is empty", () => {
    renderWithProviders(<LoginScreen />);

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows generic error on non-401 failure", () => {
    useLoginMock.mockReturnValue({
      mutateAsync: vi.fn().mockRejectedValue(new Error("Server error")),
      isPending: false,
      error: { status: 500, message: "Server error" },
    });
    renderWithProviders(<LoginScreen />);
    expect(screen.getByText("Login failed")).toBeTruthy();
  });

  it("shows the rate-limit message on 429", () => {
    useLoginMock.mockReturnValue({
      mutateAsync: vi.fn().mockRejectedValue(new Error("Too many attempts")),
      isPending: false,
      error: { status: 429, message: "Too many attempts" },
    });
    renderWithProviders(<LoginScreen />);
    expect(screen.getByText("Demasiados intentos, probá más tarde")).toBeTruthy();
  });

  it("links to the password recovery screen", () => {
    renderWithProviders(<LoginScreen />);

    expect(
      screen.getByRole("link", { name: /forgot your password/i }).getAttribute("href"),
    ).toBe("/forgot-password");
  });

  it("offers a resend action on 403 Email not verified (D5)", () => {
    const resend = vi.fn();
    useLoginMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: { status: 403, body: { detail: "Email not verified" } },
    });
    useResendVerificationMock.mockReturnValue({
      mutate: resend,
      isPending: false,
      isSuccess: false,
    });
    renderWithProviders(<LoginScreen />);

    expect(screen.getByText(/email is not verified/i)).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Email"), {
      target: { value: "dan@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reenviar correo" }));

    expect(resend).toHaveBeenCalledWith({ email: "dan@example.com" });
  });

  it("does not offer the resend action on a plain 401", () => {
    useLoginMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: { status: 401, message: "Invalid credentials" },
    });
    renderWithProviders(<LoginScreen />);

    expect(screen.queryByRole("button", { name: "Reenviar correo" })).toBeNull();
  });
});