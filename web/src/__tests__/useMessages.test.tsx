import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useMessages, MESSAGES_PAGE_SIZE } from "../queries/useMessages";
import type { Message } from "../queries/useMessages";
import { api } from "../lib/api";

// NOTE: every expectation below is derived from MESSAGES_PAGE_SIZE so the
// suite stays valid for any page-size value (e.g. the temporary live-test
// variant of 10 vs the production 50).

vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockedGet = api.get as unknown as Mock;

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

function msg(id: number): Message {
  return {
    id,
    role: id % 2 === 0 ? "assistant" : "user",
    content_text: `msg-${id}`,
  };
}

/** A raw API window: ids `top`, `top-1`, ... (newest-first), `count` items. */
function windowOf(top: number, count: number): Message[] {
  return Array.from({ length: count }, (_, i) => msg(top - i));
}

function uniqueIds(messages: Message[]): number {
  return new Set(messages.map((m) => m.id)).size;
}

const PS = MESSAGES_PAGE_SIZE;

describe("useMessages pagination", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("exposes the newest window oldest-first; a full batch means hasMore", async () => {
    mockedGet.mockResolvedValueOnce(windowOf(PS, PS)); // ids 1..PS
    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.messages.length).toBe(PS));
    expect(result.current.messages[0].id).toBe(1);
    expect(result.current.messages[PS - 1].id).toBe(PS);
    expect(mockedGet).toHaveBeenCalledWith(
      `/api/sessions/ses-1/messages?limit=${PS}`,
    );
    expect(result.current.hasMore).toBe(true);
  });

  it("loadOlder fetches the next keyset page and prepends it in order", async () => {
    mockedGet
      .mockResolvedValueOnce(windowOf(2 * PS, PS)) // ids PS+1..2*PS
      .mockResolvedValueOnce(windowOf(PS, PS)); // ids 1..PS
    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));

    await act(async () => {
      await result.current.loadOlder();
    });

    // `before` = the oldest currently loaded id (keyset cursor).
    expect(mockedGet).toHaveBeenLastCalledWith(
      `/api/sessions/ses-1/messages?limit=${PS}&before=${PS + 1}`,
    );
    expect(result.current.messages.length).toBe(2 * PS);
    expect(result.current.messages[0].id).toBe(1);
    expect(result.current.messages[2 * PS - 1].id).toBe(2 * PS);
    expect(uniqueIds(result.current.messages)).toBe(2 * PS);
    expect(result.current.hasMore).toBe(true);
  });

  it("dedupes a message that appears in two windows (boundary overlap)", async () => {
    mockedGet
      .mockResolvedValueOnce(windowOf(2 * PS, PS))
      // Overlapping batch: repeats id PS+1 even though the keyset cursor
      // should exclude it — the merge must never render it twice.
      .mockResolvedValueOnce([
        msg(PS + 1),
        ...windowOf(PS, PS - 1),
      ]);
    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));

    await act(async () => {
      await result.current.loadOlder();
    });

    // 2*PS fetched items, 1 duplicate dropped.
    expect(result.current.messages.length).toBe(2 * PS - 1);
    expect(uniqueIds(result.current.messages)).toBe(2 * PS - 1);
    expect(
      result.current.messages.filter((m) => m.id === PS + 1).length,
    ).toBe(1);
  });

  it("a short older batch flips hasMore off and blocks further loads", async () => {
    mockedGet
      .mockResolvedValueOnce(windowOf(2 * PS, PS))
      .mockResolvedValueOnce(windowOf(PS, PS - 1)); // history ends here
    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));

    await act(async () => {
      await result.current.loadOlder();
    });

    expect(result.current.messages.length).toBe(2 * PS - 1);
    expect(result.current.hasMore).toBe(false);

    const callsAfterShortBatch = mockedGet.mock.calls.length;
    await act(async () => {
      await result.current.loadOlder();
    });
    expect(mockedGet.mock.calls.length).toBe(callsAfterShortBatch);
  });

  it("an empty older batch marks the end without adding a page", async () => {
    mockedGet
      .mockResolvedValueOnce(windowOf(PS, PS))
      .mockResolvedValueOnce([]);
    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));

    await act(async () => {
      await result.current.loadOlder();
    });

    expect(result.current.messages.length).toBe(PS);
    expect(result.current.hasMore).toBe(false);
  });

  it("refetch refreshes the newest window and rescues messages that slid out of it", async () => {
    mockedGet
      .mockResolvedValueOnce(windowOf(2 * PS, PS)) // base: PS+1..2*PS
      .mockResolvedValueOnce(windowOf(PS, PS)) // older: 1..PS
      // After a turn the newest window slides up by 2 (ids PS+3..2*PS+2);
      // ids PS+1 and PS+2 fall out of the window and must survive the
      // refetch via demotion of the previous window, or the history grows
      // a gap.
      .mockResolvedValueOnce(windowOf(2 * PS + 2, PS));
    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));
    await act(async () => {
      await result.current.loadOlder();
    });
    expect(result.current.messages.length).toBe(2 * PS);

    await act(async () => {
      await result.current.refetch();
    });

    expect(result.current.messages.length).toBe(2 * PS + 2);
    expect(uniqueIds(result.current.messages)).toBe(2 * PS + 2);
    expect(result.current.messages[0].id).toBe(1);
    expect(result.current.messages[2 * PS + 1].id).toBe(2 * PS + 2);
    // The refetch only hit the newest window (no before cursor).
    expect(mockedGet).toHaveBeenLastCalledWith(
      `/api/sessions/ses-1/messages?limit=${PS}`,
    );
    // The bottom-most window is still full, so paging may continue.
    expect(result.current.hasMore).toBe(true);
  });

  it("surfaces loadOlder failures without disturbing the loaded history", async () => {
    mockedGet
      .mockResolvedValueOnce(windowOf(PS, PS))
      .mockRejectedValueOnce(new Error("API error 500"));
    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));

    await act(async () => {
      await result.current.loadOlder();
    });

    expect(result.current.loadOlderError).toBe("API error 500");
    expect(result.current.messages.length).toBe(PS);
    // The bottom window is still full: retrying stays possible.
    expect(result.current.hasMore).toBe(true);
  });

  it("switching sessions drops the previous session's older pages", async () => {
    mockedGet
      .mockResolvedValueOnce(windowOf(2 * PS, PS))
      .mockResolvedValueOnce(windowOf(PS, PS))
      .mockResolvedValueOnce(windowOf(10, 3)); // session b: ids 8..10
    let sessionId: string | null = "ses-1";
    const { result, rerender } = renderHook(() => useMessages(sessionId), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));
    await act(async () => {
      await result.current.loadOlder();
    });
    expect(result.current.messages.length).toBe(2 * PS);

    sessionId = "ses-2";
    rerender();

    await waitFor(() => expect(result.current.messages.length).toBe(3));
    expect(result.current.messages[0].id).toBe(8);
    expect(result.current.messages[2].id).toBe(10);
  });
});
