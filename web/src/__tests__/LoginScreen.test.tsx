import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderWithProviders } from "./test-utils";
import LoginScreen from "../routes/LoginScreen";
import { DELETION_SCHEDULED_NOTICE } from "../components/DeleteAccountDialog";

const { useLoginMock } = vi.hoisted(() => ({
  useLoginMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useLogin: () => useLoginMock(),
}));

describe("LoginScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useLoginMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
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
});