import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useUploadFile } from "../queries/useFiles";

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
});
