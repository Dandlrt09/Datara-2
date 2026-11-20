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
vi.mock("../routes/FirstRunScreen", () => ({
  default: () => <div>first-run-screen</div>,
}));
vi.mock("../routes/LoginScreen", () => ({ default: () => <div>login-screen</div> }));
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

describe("App first-run landing (F1 / T2c)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends an unauthenticated visitor to /first-run in local mode", async () => {
    useAppConfigMock.mockReturnValue({ data: { mode: "local" }, isError: false });
    renderApp("/");

    expect(await screen.findByText("first-run-screen")).toBeTruthy();
    expect(screen.queryByText("login-screen")).toBeNull();
  });

  it("sends an unauthenticated visitor to login in hosted mode", async () => {
    useAppConfigMock.mockReturnValue({ data: { mode: "hosted" }, isError: false });
    renderApp("/");

    expect(await screen.findByText("login-screen")).toBeTruthy();
    expect(screen.queryByText("first-run-screen")).toBeNull();
  });
});
