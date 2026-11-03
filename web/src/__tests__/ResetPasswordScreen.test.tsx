import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import ResetPasswordScreen from "../routes/ResetPasswordScreen";

const { useResetPasswordMock } = vi.hoisted(() => ({
  useResetPasswordMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useResetPassword: () => useResetPasswordMock(),
}));

function fillAndSubmit(password = "newpassword123", confirm = password) {
  fireEvent.change(screen.getByLabelText("Nueva contraseña"), {
    target: { value: password },
  });
  fireEvent.change(screen.getByLabelText("Repetir contraseña"), {
    target: { value: confirm },
  });
  fireEvent.click(screen.getByRole("button", { name: "Guardar contraseña" }));
}

describe("ResetPasswordScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useResetPasswordMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue(undefined),
      isPending: false,
      isSuccess: false,
      error: null,
    });
  });

  it("renders the new-password form", () => {
    renderWithProviders(<ResetPasswordScreen />, {
      route: "/reset-password?token=abc123",
    });

    expect(
      screen.getByRole("heading", { name: "Nueva contraseña" }),
    ).toBeTruthy();
    expect(screen.getByLabelText("Nueva contraseña")).toBeTruthy();
    expect(screen.getByLabelText("Repetir contraseña")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Guardar contraseña" })).toBeTruthy();
  });

  it("reveals and hides both password fields with one toggle", () => {
    renderWithProviders(<ResetPasswordScreen />, {
      route: "/reset-password?token=abc123",
    });

    const password = screen.getByLabelText("Nueva contraseña");
    const confirm = screen.getByLabelText("Repetir contraseña");
    expect(password.getAttribute("type")).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "Mostrar contraseñas" }));
    expect(password.getAttribute("type")).toBe("text");
    expect(confirm.getAttribute("type")).toBe("text");
  });

  it("blocks the submit when the passwords do not match", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    useResetPasswordMock.mockReturnValue({
      mutateAsync,
      isPending: false,
      isSuccess: false,
      error: null,
    });
    renderWithProviders(<ResetPasswordScreen />, {
      route: "/reset-password?token=abc123",
    });

    fillAndSubmit("newpassword123", "different123");

    expect(await screen.findByText("Las contraseñas no coinciden")).toBeTruthy();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("sends the token and the new password", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    useResetPasswordMock.mockReturnValue({
      mutateAsync,
      isPending: false,
      isSuccess: false,
      error: null,
    });
    renderWithProviders(<ResetPasswordScreen />, {
      route: "/reset-password?token=abc123",
    });

    fillAndSubmit();

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        token: "abc123",
        new_password: "newpassword123",
      }),
    );
  });

  it("shows the invalid-link message on 400", () => {
    useResetPasswordMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isSuccess: false,
      error: { status: 400, message: "Invalid or expired token" },
    });
    renderWithProviders(<ResetPasswordScreen />, {
      route: "/reset-password?token=expired",
    });

    expect(screen.getByText("El enlace no es válido o ya venció")).toBeTruthy();
  });

  it("shows the short-password message on 422", () => {
    useResetPasswordMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isSuccess: false,
      error: { status: 422, message: "Password must be at least 8 characters" },
    });
    renderWithProviders(<ResetPasswordScreen />, {
      route: "/reset-password?token=abc123",
    });

    expect(
      screen.getByText("La contraseña debe tener al menos 8 caracteres"),
    ).toBeTruthy();
  });

  it("confirms the reset and links to login on success", () => {
    useResetPasswordMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isSuccess: true,
      error: null,
    });
    renderWithProviders(<ResetPasswordScreen />, {
      route: "/reset-password?token=abc123",
    });

    expect(
      screen.getByRole("heading", { name: "Contraseña actualizada" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Ir a iniciar sesión" }).getAttribute("href"),
    ).toBe("/login");
  });
});
