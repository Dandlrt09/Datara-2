import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import RegisterScreen from "../routes/RegisterScreen";

const { useRegisterMock } = vi.hoisted(() => ({
  useRegisterMock: vi.fn(),
}));

vi.mock("../queries/useAuth", () => ({
  useRegister: () => useRegisterMock(),
}));

/** Fill the form the way a person would; each call starts from a fresh render. */
function fillForm({
  name = "",
  email = "dan@example.com",
  password = "password123",
  confirm = password,
}: Partial<{
  name: string;
  email: string;
  password: string;
  confirm: string;
}> = {}) {
  if (name) fireEvent.change(screen.getByLabelText("Nombre (opcional)"), { target: { value: name } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Repetir contraseña"), { target: { value: confirm } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
}

describe("RegisterScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useRegisterMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
      error: null,
    });
  });

  it("renders the form in Spanish with real labels, not placeholders", () => {
    renderWithProviders(<RegisterScreen />);

    expect(screen.getByRole("heading", { name: "Crear cuenta" })).toBeTruthy();
    expect(screen.getByLabelText("Nombre (opcional)")).toBeTruthy();
    expect(screen.getByLabelText("Email")).toBeTruthy();
    expect(screen.getByLabelText("Contraseña")).toBeTruthy();
    expect(screen.getByLabelText("Repetir contraseña")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Crear cuenta" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Iniciá sesión" })).toBeTruthy();
  });

  it("says what happens when the name is left empty (S2)", () => {
    renderWithProviders(<RegisterScreen />);

    expect(
      screen.getByText(/si lo dejás vacío, usamos la parte local de tu email/i),
    ).toBeTruthy();
  });

  it("reveals and hides both password fields with one toggle (D3)", () => {
    renderWithProviders(<RegisterScreen />);

    const password = screen.getByLabelText("Contraseña");
    const confirm = screen.getByLabelText("Repetir contraseña");
    expect(password.getAttribute("type")).toBe("password");
    expect(confirm.getAttribute("type")).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "Mostrar contraseñas" }));
    expect(password.getAttribute("type")).toBe("text");
    expect(confirm.getAttribute("type")).toBe("text");

    fireEvent.click(screen.getByRole("button", { name: "Ocultar contraseñas" }));
    expect(password.getAttribute("type")).toBe("password");
    expect(confirm.getAttribute("type")).toBe("password");
  });

  it("blocks the submit when the passwords do not match (S3)", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    useRegisterMock.mockReturnValue({ mutateAsync, isPending: false, error: null });
    renderWithProviders(<RegisterScreen />);

    fillForm({ password: "password123", confirm: "password124" });
    submit();

    expect(await screen.findByText("Las contraseñas no coinciden")).toBeTruthy();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("blocks the submit on a short password", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    useRegisterMock.mockReturnValue({ mutateAsync, isPending: false, error: null });
    renderWithProviders(<RegisterScreen />);

    fillForm({ password: "corta", confirm: "corta" });
    submit();

    expect(
      await screen.findByText("La contraseña debe tener al menos 8 caracteres"),
    ).toBeTruthy();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("blocks the submit on an email the server would refuse", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    useRegisterMock.mockReturnValue({ mutateAsync, isPending: false, error: null });
    renderWithProviders(<RegisterScreen />);

    fillForm({ email: "noesunemail" });
    submit();

    expect(await screen.findByText("Ese email no parece válido")).toBeTruthy();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("sends the typed name with the credentials", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    useRegisterMock.mockReturnValue({ mutateAsync, isPending: false, error: null });
    renderWithProviders(<RegisterScreen />);

    fillForm({ name: "Daniel" });
    submit();

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        email: "dan@example.com",
        password: "password123",
        name: "Daniel",
      }),
    );
  });

  it("omits the name key when the field is empty (S2)", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    useRegisterMock.mockReturnValue({ mutateAsync, isPending: false, error: null });
    renderWithProviders(<RegisterScreen />);

    fillForm();
    submit();

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        email: "dan@example.com",
        password: "password123",
      }),
    );
  });

  it("rates the password strength without blocking (S4/D6)", () => {
    renderWithProviders(<RegisterScreen />);
    const password = screen.getByLabelText("Contraseña");

    fireEvent.change(password, { target: { value: "abc" } });
    expect(screen.getByText("Débil")).toBeTruthy();

    fireEvent.change(password, { target: { value: "Password1" } });
    expect(screen.getByText("Media")).toBeTruthy();

    fireEvent.change(password, { target: { value: "Password1!abcd" } });
    expect(screen.getByText("Fuerte")).toBeTruthy();
  });

  it("tells the person the email already has an account", () => {
    useRegisterMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: { status: 409, message: "Conflict" },
    });
    renderWithProviders(<RegisterScreen />);

    expect(screen.getByText("Ese email ya tiene una cuenta")).toBeTruthy();
  });

  it("shows the rate-limit message on 429", () => {
    useRegisterMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: { status: 429, message: "Too many attempts" },
    });
    renderWithProviders(<RegisterScreen />);

    expect(screen.getByText("Demasiados intentos, probá más tarde")).toBeTruthy();
  });

  it("shows a data-check message on 422", () => {
    useRegisterMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: { status: 422, message: "Invalid email address" },
    });
    renderWithProviders(<RegisterScreen />);

    expect(screen.getByText("Revisá los datos ingresados")).toBeTruthy();
  });

  it("shows a Spanish generic message on an unexpected failure", () => {
    useRegisterMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: { status: 500, message: "Server error" },
    });
    renderWithProviders(<RegisterScreen />);

    expect(
      screen.getByText("No pudimos crear la cuenta. Vuelve a intentarlo."),
    ).toBeTruthy();
  });
});
