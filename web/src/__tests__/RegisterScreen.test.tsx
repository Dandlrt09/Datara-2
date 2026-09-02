import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import RegisterScreen from "../routes/RegisterScreen";

const { useRegisterMock } = vi.hoisted(() => ({
  useRegisterMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useRegister: () => useRegisterMock(),
}));

describe("RegisterScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useRegisterMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
  });

  it("renders the form", () => {
    renderWithProviders(<RegisterScreen />);
    expect(screen.getByRole("heading", { name: /register/i })).toBeTruthy();
    expect(screen.getByPlaceholderText("Email")).toBeTruthy();
    expect(screen.getByPlaceholderText("Password (8+ characters)")).toBeTruthy();
    expect(screen.getByRole("button", { name: /register/i })).toBeTruthy();
  });

  it("shows error message on 409 conflict", () => {
    useRegisterMock.mockReturnValue({
      mutateAsync: vi.fn().mockRejectedValue(new Error("Conflict")),
      isPending: false,
      error: { status: 409, message: "Conflict" },
    });
    renderWithProviders(<RegisterScreen />);
    expect(screen.getByText("Email already registered")).toBeTruthy();
  });

  it("shows generic error on non-409 failure", () => {
    useRegisterMock.mockReturnValue({
      mutateAsync: vi.fn().mockRejectedValue(new Error("Server error")),
      isPending: false,
      error: { status: 500, message: "Server error" },
    });
    renderWithProviders(<RegisterScreen />);
    expect(screen.getByText("Registration failed")).toBeTruthy();
  });
});