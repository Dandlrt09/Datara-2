import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { useAppConfigMock } = vi.hoisted(() => ({ useAppConfigMock: vi.fn() }));

vi.mock("../queries/useAppConfig", async () => ({
  ...(await vi.importActual<typeof import("../queries/useAppConfig")>(
    "../queries/useAppConfig",
  )),
  useAppConfig: () => useAppConfigMock(),
}));
vi.mock("../routes/LoginScreen", () => ({ default: () => <div>login-screen</div> }));
vi.mock("../routes/RegisterScreen", () => ({ default: () => <div>register-screen</div> }));
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

function renderApp(route: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const EMAIL_ROUTES: [string, string][] = [
  ["/register", "register-screen"],
  ["/check-email", "check-email-screen"],
  ["/verify-email?token=abc", "verify-email-screen"],
  ["/forgot-password", "forgot-password-screen"],
  ["/reset-password?token=abc", "reset-password-screen"],
];

describe("App deployment mode (F1 / T1)", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each(EMAIL_ROUTES)("hides %s in local mode (sends to login)", async (route, marker) => {
    useAppConfigMock.mockReturnValue({ data: { mode: "local" }, isError: false });
    renderApp(route);

    expect(await screen.findByText("login-screen")).toBeTruthy();
    expect(screen.queryByText(marker)).toBeNull();
  });

  it.each(EMAIL_ROUTES)("keeps %s reachable in hosted mode", async (route, marker) => {
    useAppConfigMock.mockReturnValue({ data: { mode: "hosted" }, isError: false });
    renderApp(route);

    expect(await screen.findByText(marker)).toBeTruthy();
  });

  it("fails open to the email screens when the mode cannot be read", async () => {
    useAppConfigMock.mockReturnValue({ data: undefined, isError: true });
    renderApp("/register");

    expect(await screen.findByText("register-screen")).toBeTruthy();
  });

  it("keeps login and the app shell reachable in local mode", async () => {
    useAppConfigMock.mockReturnValue({ data: { mode: "local" }, isError: false });
    renderApp("/app");

    expect(await screen.findByText("app-shell")).toBeTruthy();
  });
});
