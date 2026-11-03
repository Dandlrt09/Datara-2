import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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

describe("App recovery routes", () => {
  it.each([
    ["/check-email", "check-email-screen"],
    ["/verify-email?token=abc", "verify-email-screen"],
    ["/forgot-password", "forgot-password-screen"],
    ["/reset-password?token=abc", "reset-password-screen"],
  ])("routes %s to its screen", async (route, marker) => {
    renderApp(route);

    expect(await screen.findByText(marker)).toBeTruthy();
  });

  it("keeps the unknown-path catch-all pointing at login", async () => {
    renderApp("/no-existe");

    expect(await screen.findByText("login-screen")).toBeTruthy();
  });
});
