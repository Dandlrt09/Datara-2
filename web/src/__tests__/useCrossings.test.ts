/* Wire pins for the crossing hooks (F5 / T5).
 *
 * The panel tests mock these hooks, so a typo in a route prefix or a wrong
 * HTTP method would ship unnoticed. This file stubs `fetch` (the same seam
 * `useFiles.test.tsx` uses) and pins the exact path, method and JSON body of
 * each call.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import {
  useConfirmCrossing,
  useCrossing,
  useCrossingFiles,
  useCrossingProfile,
  useDeleteCrossing,
  useProposeCrossing,
} from "../queries/useCrossings";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  // No JSX: this file is `.ts` (the path the task names), so the provider is
  // built with createElement.
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
  return wrapper;
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}

/** The URL and RequestInit of the first `fetch` call. */
function firstCall(fetchMock: ReturnType<typeof vi.fn>) {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return { url, init };
}

describe("useCrossings wire", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("GETs the session's active crossing", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ crossing: null }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useCrossing("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const { url, init } = firstCall(fetchMock);
    expect(url).toBe("/api/sessions/ses-1/crossings");
    expect(init.method).toBeUndefined(); // api.get: GET is the fetch default
  });

  it("GETs one session file page for the pickers", async () => {
    const fetchMock = vi.fn(async () => jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useCrossingFiles("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const { url, init } = firstCall(fetchMock);
    expect(url).toBe("/api/sessions/ses-1/files?limit=200");
    expect(init.method).toBeUndefined();
  });

  it("GETs a file's profile for its column options", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ file_id: 5 }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useCrossingProfile(5), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const { url, init } = firstCall(fetchMock);
    expect(url).toBe("/api/files/5/profile");
    expect(init.method).toBeUndefined();
  });

  it("POSTs the two files to the proposal endpoint as JSON", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ proposal: null, code: null }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useProposeCrossing("ses-1"), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({ left_file_id: 1, right_file_id: 2 });
    });

    const { url, init } = firstCall(fetchMock);
    expect(url).toBe("/api/sessions/ses-1/crossings/propose");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      left_file_id: 1,
      right_file_id: 2,
    });
  });

  it("POSTs the confirmed recipe as JSON", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ id: 7 }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useConfirmCrossing("ses-1"), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({
        left_file_id: 1,
        right_file_id: 2,
        left_key: "id",
        right_key: "customer_id",
        how: "left",
      });
    });

    const { url, init } = firstCall(fetchMock);
    expect(url).toBe("/api/sessions/ses-1/crossings");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      left_file_id: 1,
      right_file_id: 2,
      left_key: "id",
      right_key: "customer_id",
      how: "left",
    });
  });

  it("DELETEs the session's crossing", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({}, 204));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useDeleteCrossing("ses-1"), {
      wrapper: makeWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync();
    });

    const { url, init } = firstCall(fetchMock);
    expect(url).toBe("/api/sessions/ses-1/crossings");
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
  });
});
