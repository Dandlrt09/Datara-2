import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { ApiError } from "../lib/api";

const { useDataFolderMock, chooseMock, useChooseDataFolderMock } = vi.hoisted(
  () => ({
    useDataFolderMock: vi.fn(),
    chooseMock: vi.fn(),
    useChooseDataFolderMock: vi.fn(),
  })
);

vi.mock("../queries/useDataFolder", () => ({
  useDataFolder: () => useDataFolderMock(),
  useChooseDataFolder: () => useChooseDataFolderMock(),
}));

// Screens the gate must not show while the folder is undecided, plus the
// normal landing once it is decided. DataFolderScreen itself is left real.
vi.mock("../routes/LoginScreen", () => ({ default: () => <div>login-screen</div> }));
vi.mock("../routes/RegisterScreen", () => ({
  default: () => <div>register-screen</div>,
}));
vi.mock("../routes/CheckEmailScreen", () => ({
  default: () => <div>check-email-screen</div>,
}));
vi.mock("../routes/VerifyEmailScreen", () => ({
  default: () => <div>verify-email-screen</div>,
}));
vi.mock("../routes/ForgotPasswordScreen", () => ({
  default: () => <div>forgot-password-screen</div>,
}));
vi.mock("../routes/ResetPasswordScreen", () => ({
  default: () => <div>reset-password-screen</div>,
}));
vi.mock("../routes/TermsScreen", () => ({ default: () => <div>terms-screen</div> }));
vi.mock("../routes/AppShell", () => ({ default: () => <div>app-shell</div> }));

import App from "../App";
import DataFolderScreen from "../routes/DataFolderScreen";

const UNDECIDED = {
  decided: false,
  path: "/home/dan/datos",
  default_path: "/home/dan/.local/share/datara",
};

const HEADING = /dónde guardamos tus datos/i;

function setDecisionError(error: unknown = null) {
  useChooseDataFolderMock.mockReturnValue({
    mutateAsync: chooseMock,
    isPending: false,
    error,
  });
}

function renderScreen(onContinue?: () => void) {
  return renderWithProviders(
    <DataFolderScreen
      currentPath={UNDECIDED.path}
      defaultPath={UNDECIDED.default_path}
      onContinue={onContinue}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useDataFolderMock.mockReturnValue({
    data: UNDECIDED,
    isLoading: false,
    isError: false,
  });
  setDecisionError();
});

describe("data-folder gate (S1/S5)", () => {
  it("shows the data-folder screen while undecided, not the login", async () => {
    renderWithProviders(<App />, { route: "/login" });

    expect(await screen.findByRole("heading", { name: HEADING })).toBeTruthy();
    expect(screen.queryByText("login-screen")).toBeNull();
  });

  it("renders the app normally once decided", async () => {
    useDataFolderMock.mockReturnValue({
      data: { ...UNDECIDED, decided: true },
      isLoading: false,
      isError: false,
    });

    renderWithProviders(<App />, { route: "/login" });

    expect(await screen.findByText("login-screen")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: HEADING })).toBeNull();
  });
});

describe("DataFolderScreen (S1/S6)", () => {
  it("shows the folder that would be used and the recommended one", () => {
    renderScreen();

    expect(screen.getByText(UNDECIDED.path)).toBeTruthy();
    expect(screen.getByText(UNDECIDED.default_path)).toBeTruthy();
  });

  it("accepts a typed path and sends it to PUT", async () => {
    chooseMock.mockResolvedValue({
      ...UNDECIDED,
      decided: true,
      path: "/otra/carpeta",
      synced_client: null,
    });
    renderScreen();

    fireEvent.change(screen.getByLabelText("Carpeta de datos"), {
      target: { value: "/otra/carpeta" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Usar esta carpeta" }));

    await waitFor(() => expect(chooseMock).toHaveBeenCalledWith("/otra/carpeta"));
  });

  it("sends default_path when the analyst takes the recommended folder", async () => {
    chooseMock.mockResolvedValue({
      ...UNDECIDED,
      decided: true,
      synced_client: null,
    });
    renderScreen();

    fireEvent.click(
      screen.getByRole("button", { name: "Usar la carpeta recomendada" })
    );

    await waitFor(() =>
      expect(chooseMock).toHaveBeenCalledWith(UNDECIDED.default_path)
    );
  });

  it("tells the analyst to restart after a decision, without faking a reload", async () => {
    chooseMock.mockResolvedValue({
      ...UNDECIDED,
      decided: true,
      path: "/otra/carpeta",
      synced_client: null,
    });
    renderScreen();

    fireEvent.click(
      screen.getByRole("button", { name: "Usar la carpeta recomendada" })
    );

    expect(await screen.findByText(/volvé a abrir Datara/i)).toBeTruthy();
  });

  it("names the sync risk once and still lets the analyst continue", async () => {
    const onContinue = vi.fn();
    chooseMock.mockResolvedValue({
      decided: true,
      path: "/home/dan/Dropbox/datos",
      default_path: UNDECIDED.default_path,
      synced_client: "Dropbox",
    });
    renderScreen(onContinue);

    fireEvent.change(screen.getByLabelText("Carpeta de datos"), {
      target: { value: "/home/dan/Dropbox/datos" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Usar esta carpeta" }));

    const warning = await screen.findByRole("alert");
    expect(warning.textContent).toContain("Dropbox");

    const continueButton = screen.getByRole("button", {
      name: "Continuar",
    }) as HTMLButtonElement;
    expect(continueButton.disabled).toBe(false);
    fireEvent.click(continueButton);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("shows no sync warning when the response carries no synced client", async () => {
    chooseMock.mockResolvedValue({
      ...UNDECIDED,
      decided: true,
      path: "/otra/carpeta",
      synced_client: null,
    });
    renderScreen();

    fireEvent.click(
      screen.getByRole("button", { name: "Usar la carpeta recomendada" })
    );
    await screen.findByText(/volvé a abrir Datara/i);

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each([
    ["invalid_path", 422, /absoluta/i],
    ["path_not_writable", 422, /no se puede escribir/i],
    ["already_decided", 409, /ya fue decidida/i],
  ])("renders its own message for %s", (code, status, expected) => {
    setDecisionError(
      new ApiError(status, { detail: { code, message: "server text" } })
    );
    renderScreen();

    expect(screen.getByRole("alert").textContent).toMatch(expected);
  });
});
