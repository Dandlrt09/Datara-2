import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import ForgotPasswordScreen from "../routes/ForgotPasswordScreen";

const { useForgotPasswordMock } = vi.hoisted(() => ({
  useForgotPasswordMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useForgotPassword: () => useForgotPasswordMock(),
}));

const SUCCESS = "Si esa dirección tiene una cuenta, te enviamos un enlace para restablecerla";

function submit(email: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar enlace" }));
}

describe("ForgotPasswordScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useForgotPasswordMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue(undefined),
      isPending: false,
    });
  });

  it("renders the email form", () => {
    renderWithProviders(<ForgotPasswordScreen />);

    expect(
      screen.getByRole("heading", { name: "Recuperar contraseña" }),
    ).toBeTruthy();
    expect(screen.getByLabelText("Email")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Enviar enlace" })).toBeTruthy();
  });

  it("shows the same non-enumerating message when the email exists", async () => {
    renderWithProviders(<ForgotPasswordScreen />);

    submit("dan@example.com");

    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe(SUCCESS);
  });

  it("shows the same non-enumerating message when the request fails (D6)", async () => {
    useForgotPasswordMock.mockReturnValue({
      mutateAsync: vi.fn().mockRejectedValue(new Error("boom")),
      isPending: false,
    });
    renderWithProviders(<ForgotPasswordScreen />);

    submit("desconocido@example.com");

    await waitFor(() => expect(screen.getByRole("status")).toBeTruthy());
    expect(screen.getByRole("status").textContent).toBe(SUCCESS);
  });

  it("offers the way back to login", () => {
    renderWithProviders(<ForgotPasswordScreen />);

    expect(
      screen.getByRole("link", { name: "Volver a iniciar sesión" }).getAttribute("href"),
    ).toBe("/login");
  });
});
