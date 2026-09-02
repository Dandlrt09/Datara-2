import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import LoginScreen from "../routes/LoginScreen";

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

  it("shows generic error on non-401 failure", () => {
    useLoginMock.mockReturnValue({
      mutateAsync: vi.fn().mockRejectedValue(new Error("Server error")),
      isPending: false,
      error: { status: 500, message: "Server error" },
    });
    renderWithProviders(<LoginScreen />);
    expect(screen.getByText("Login failed")).toBeTruthy();
  });
});