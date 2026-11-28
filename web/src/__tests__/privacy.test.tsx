import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  renderHook,
  act,
  waitFor,
  screen,
  fireEvent,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { renderWithProviders } from "./test-utils";
import {
  useUpdateFilePrivacy,
  useUpdateSessionPrivacy,
} from "../queries/usePrivacy";
import { PrivacyPanel } from "../components/PrivacyPanel";

/** QueryClient wrapper for the hook-level tests (mirrors useFiles.test.tsx). */
function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return wrapper;
}

/** Minimal fetch Response shape the api client reads (ok/status/json). */
function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

/** Route a mocked fetch by "METHOD url" and record every call. */
function mockFetch(routes: Record<string, (init: RequestInit) => unknown>) {
  return vi.fn(async (url: string, init: RequestInit = {}) => {
    const method = (init.method ?? "GET").toUpperCase();
    const handler = routes[`${method} ${url}`];
    if (!handler) throw new Error(`Unhandled request: ${method} ${url}`);
    return jsonResponse(handler(init));
  });
}

const sessionPrivacy = {
  session_id: "ses-1",
  privacy_level: "full",
  levels: ["full", "aggregates", "schema", "masked"],
  files: [
    {
      file_id: 42,
      filename: "ventas.csv",
      privacy_level: "masked",
      effective_level: "masked",
      column_aliases: null,
    },
  ],
};

const preview = {
  profiles: [
    {
      file_id: 42,
      filename: "clientes-2026.xlsx",
      format: "xlsx",
      path: "dataset_1.xlsx",
      row_count: 2,
      sheet_index: 0,
      profile: {
        columns: [{ name: "nombre", dtype: "object" }],
        stats: {},
        sample: [{ nombre: "Xxxxx" }],
      },
    },
  ],
  unprofiled_files: [],
};

describe("privacy mutations", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("useUpdateFilePrivacy sends the level as a PATCH body", async () => {
    const fetchMock = mockFetch({
      "PATCH /api/files/42/privacy": () => sessionPrivacy.files[0],
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUpdateFilePrivacy(), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ fileId: 42, privacyLevel: "schema" });
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/files/42/privacy");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({
      privacy_level: "schema",
    });
  });

  it("useUpdateFilePrivacy sends null to clear the override (inherit)", async () => {
    const fetchMock = mockFetch({
      "PATCH /api/files/42/privacy": () => sessionPrivacy.files[0],
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUpdateFilePrivacy(), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ fileId: 42, privacyLevel: null });
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ privacy_level: null });
  });

  it("useUpdateSessionPrivacy sends the level as a PUT body", async () => {
    const fetchMock = mockFetch({
      "PUT /api/sessions/ses-1/privacy": () => sessionPrivacy,
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUpdateSessionPrivacy(), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({
        sessionId: "ses-1",
        privacyLevel: "aggregates",
      });
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/sessions/ses-1/privacy");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({
      privacy_level: "aggregates",
    });
  });
});

describe("PrivacyPanel", () => {
  let fetchMock: ReturnType<typeof mockFetch>;

  beforeEach(() => {
    fetchMock = mockFetch({
      "GET /api/sessions/ses-1/privacy": () => sessionPrivacy,
      "GET /api/sessions/ses-1/privacy/preview": () => preview,
      "PUT /api/sessions/ses-1/privacy": () => sessionPrivacy,
      "PATCH /api/files/42/privacy": () => sessionPrivacy.files[0],
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the session and per-file selectors from the session privacy", async () => {
    renderWithProviders(
      <PrivacyPanel sessionId="ses-1" open onClose={() => {}} />,
    );

    // Wait for the loaded rows: the session selector renders before the query
    // resolves, the per-file selector only appears once it has.
    const fileSelect = await screen.findByLabelText(
      "Privacidad de ventas.csv",
    );
    expect((fileSelect as HTMLSelectElement).value).toBe("masked");

    const sessionSelect = screen.getByLabelText(
      "Nivel de privacidad de la sesión",
    );
    expect((sessionSelect as HTMLSelectElement).value).toBe("full");
    // The inherit option is offered for a file override.
    expect(
      screen.getByRole("option", { name: "Heredar de la sesión" }),
    ).toBeTruthy();
  });

  it("changing a file selector sends the PATCH for that file", async () => {
    renderWithProviders(
      <PrivacyPanel sessionId="ses-1" open onClose={() => {}} />,
    );

    const fileSelect = await screen.findByLabelText("Privacidad de ventas.csv");
    fireEvent.change(fileSelect, { target: { value: "inherit" } });

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          url === "/api/files/42/privacy" &&
          (init as RequestInit).method === "PATCH",
      );
      expect(call).toBeTruthy();
      expect(JSON.parse((call![1] as RequestInit).body as string)).toEqual({
        privacy_level: null,
      });
    });
  });

  it("changing the session selector sends the session PUT", async () => {
    renderWithProviders(
      <PrivacyPanel sessionId="ses-1" open onClose={() => {}} />,
    );

    const sessionSelect = await screen.findByLabelText(
      "Nivel de privacidad de la sesión",
    );
    fireEvent.change(sessionSelect, { target: { value: "aggregates" } });

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          url === "/api/sessions/ses-1/privacy" &&
          (init as RequestInit).method === "PUT",
      );
      expect(call).toBeTruthy();
      expect(JSON.parse((call![1] as RequestInit).body as string)).toEqual({
        privacy_level: "aggregates",
      });
    });
  });

  it("renders the outgoing preview the server returns", async () => {
    renderWithProviders(
      <PrivacyPanel sessionId="ses-1" open onClose={() => {}} />,
    );

    // The preview is lazy until the viewer is opened.
    fireEvent.click(screen.getByRole("button", { name: "Ver qué se envía" }));

    const pre = await screen.findByTestId("privacy-preview");
    expect(pre.textContent).toContain("clientes-2026.xlsx");
    expect(pre.textContent).toContain("dataset_1.xlsx");
  });
});
