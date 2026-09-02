import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { createQueryClient } from "../lib/queryClient";

describe("QueryClient production policies (C-1)", () => {
  let client = createQueryClient();
  beforeEach(() => { client = createQueryClient(); });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

  it("defaults: retry=0, refetchOnWindowFocus=false (R-QueryClient-1)", () => {
    const d = client.getDefaultOptions();
    expect(d.queries?.retry).toBe(0);
    expect(d.queries?.refetchOnWindowFocus).toBe(false);
    expect(d.mutations?.retry).toBe(0);
  });

  it("fail-fast: failing query fetches exactly once (R-QueryClient-2)", async () => {
    const fetchSpy = vi.fn(() => Promise.reject(new Error("API error")));
    const { result } = renderHook(
      () => useQuery({ queryKey: ["test-fail"], queryFn: fetchSpy }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("focus: window focus does not refetch (R-QueryClient-3)", async () => {
    const fetchSpy = vi.fn().mockResolvedValue("data");
    const { result } = renderHook(
      () => useQuery({ queryKey: ["test-focus"], queryFn: fetchSpy }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    fetchSpy.mockClear();
    act(() => { window.dispatchEvent(new Event("focus")); });
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});