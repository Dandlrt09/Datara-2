import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useArchives, ARCHIVES_PAGE_SIZE } from "../queries/useArchives";
import type { Archive } from "../queries/useArchives";

const { apiGetMock } = vi.hoisted(() => ({ apiGetMock: vi.fn() }));

// Mock the transport only: the real hook (and its keyset logic) runs.
vi.mock("../lib/api", () => ({
  api: { get: (...args: unknown[]) => apiGetMock(...args) },
}));

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return wrapper;
}

function archiveOf(id: number): Archive {
  return {
    id,
    name: `archivo-${id}`,
    chat_session: "ses-1",
    created_at: "2026-01-01T00:00:00Z",
    files: [],
    row_count: null,
    column_count: null,
  };
}

describe("useArchives keyset pagination", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("fetches the first page at ARCHIVES_PAGE_SIZE without a cursor", async () => {
    const firstPage = Array.from({ length: ARCHIVES_PAGE_SIZE }, (_, i) =>
      archiveOf(ARCHIVES_PAGE_SIZE * 2 - i),
    );
    apiGetMock.mockResolvedValueOnce(firstPage);

    const { result } = renderHook(() => useArchives(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() =>
      expect(result.current.data?.pages[0].length).toBe(ARCHIVES_PAGE_SIZE),
    );

    expect(apiGetMock.mock.calls[0][0]).toBe(
      `/api/archives?limit=${ARCHIVES_PAGE_SIZE}`,
    );
    // A full page means a next page may exist.
    expect(result.current.hasNextPage).toBe(true);
  });

  it("uses the LAST item's id as the next cursor", async () => {
    const firstPage = Array.from({ length: ARCHIVES_PAGE_SIZE }, (_, i) =>
      archiveOf(ARCHIVES_PAGE_SIZE * 2 - i),
    );
    const secondPage = [archiveOf(3), archiveOf(2), archiveOf(1)];
    apiGetMock
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);

    const { result } = renderHook(() => useArchives(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() =>
      expect(result.current.data?.pages[0].length).toBe(ARCHIVES_PAGE_SIZE),
    );

    await act(async () => {
      await result.current.fetchNextPage();
    });

    const lastOnFirstPage = firstPage[firstPage.length - 1].id;
    expect(apiGetMock.mock.calls[1][0]).toBe(
      `/api/archives?limit=${ARCHIVES_PAGE_SIZE}&before=${lastOnFirstPage}`,
    );
    await waitFor(() => expect(result.current.data?.pages.length).toBe(2));
  });

  it("reports hasNextPage === false on a short first page", async () => {
    apiGetMock.mockResolvedValueOnce([archiveOf(2), archiveOf(1)]);

    const { result } = renderHook(() => useArchives(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.data?.pages[0].length).toBe(2));

    expect(result.current.hasNextPage).toBe(false);
  });
});
