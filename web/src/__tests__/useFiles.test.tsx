import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useUploadFile, UploadError } from "../queries/useFiles";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return wrapper;
}

describe("useUploadFile", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("threads the AbortSignal into the upload fetch", async () => {
    // Never-resolving fetch keeps the mutation in-flight for inspection.
    const fetchMock = vi.fn(
      (..._args: unknown[]) => new Promise<Response>(() => {}),
    );
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useUploadFile(), { wrapper });

    const controller = new AbortController();
    result.current.mutate({
      sessionId: "ses-1",
      file: new File(["name,age\nAlice,30\n"], "a.csv"),
      signal: controller.signal,
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBe(controller.signal);

    controller.abort();
    expect((init.signal as AbortSignal).aborted).toBe(true);
  });

  it("works without a signal (backwards compatible)", async () => {
    const fetchMock = vi.fn(
      (..._args: unknown[]) => new Promise<Response>(() => {}),
    );
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useUploadFile(), { wrapper });

    result.current.mutate({
      sessionId: "ses-1",
      file: new File(["name,age\nAlice,30\n"], "a.csv"),
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBeUndefined();
  });

  it("rejects with an UploadError carrying the status and server detail", async () => {
    const detail =
      "A file named 'a.csv' already exists in this session. Delete it first.";
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 409,
      json: async () => ({ detail }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUploadFile(), {
      wrapper: makeWrapper(),
    });

    let caught: unknown;
    try {
      await result.current.mutateAsync({
        sessionId: "ses-1",
        file: new File(["x"], "a.csv"),
      });
    } catch (e) {
      caught = e;
    }

    expect(caught).toBeInstanceOf(UploadError);
    expect((caught as UploadError).status).toBe(409);
    expect((caught as UploadError).message).toBe(detail);
  });

  it("falls back to the status message when the error body is not JSON", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 400,
      json: async () => {
        throw new SyntaxError("Unexpected token < in JSON");
      },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUploadFile(), {
      wrapper: makeWrapper(),
    });

    let caught: unknown;
    try {
      await result.current.mutateAsync({
        sessionId: "ses-1",
        file: new File(["x"], "a.csv"),
      });
    } catch (e) {
      caught = e;
    }

    expect(caught).toBeInstanceOf(UploadError);
    expect((caught as UploadError).status).toBe(400);
    expect((caught as UploadError).message).toBe("Upload failed: 400");
  });
});
