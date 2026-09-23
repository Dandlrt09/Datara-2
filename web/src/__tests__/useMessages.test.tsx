import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useMessages, MESSAGES_PAGE_SIZE } from "../queries/useMessages";
import type { Message } from "../queries/useMessages";
import { api } from "../lib/api";
import { useChatStore } from "../stores/useChatStore";

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
    // The chat store is a global Zustand singleton — reset truncation residue.
    useChatStore.setState({ historyReset: null });
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

  it("a history-reset signal drops stale older windows and refetches only the newest window", async () => {
    // Newest window: ids PS+1..2*PS. Older window fetched BEFORE the edit:
    // ids 1..PS. After a truncating edit the server no longer returns those
    // older rows, so the reset must drop the whole older window and refetch
    // ONLY the newest page — never demoting the stale snapshot back in.
    mockedGet
      .mockResolvedValueOnce(windowOf(2 * PS, PS)) // newest: PS+1..2*PS
      .mockResolvedValueOnce(windowOf(PS, PS)) // older: 1..PS
      .mockResolvedValueOnce(windowOf(2 * PS, PS)); // refetched newest
    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));

    await act(async () => {
      await result.current.loadOlder();
    });
    expect(result.current.messages.length).toBe(2 * PS);
    expect(result.current.messages.map((m) => m.id)).toContain(1);

    await act(async () => {
      useChatStore.getState().bumpHistoryReset("ses-1");
    });

    // The stale older row is gone and only the newest window remains.
    await waitFor(() => expect(result.current.messages.length).toBe(PS));
    expect(result.current.messages.map((m) => m.id)).not.toContain(1);
    // The refetch hit the newest window only (no before cursor).
    expect(mockedGet).toHaveBeenLastCalledWith(
      `/api/sessions/ses-1/messages?limit=${PS}`,
    );
  });

  it("ignores a history-reset signal for a different session", async () => {
    mockedGet
      .mockResolvedValueOnce(windowOf(2 * PS, PS))
      .mockResolvedValueOnce(windowOf(PS, PS));
    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));

    await act(async () => {
      await result.current.loadOlder();
    });
    expect(result.current.messages.length).toBe(2 * PS);
    const callsBefore = mockedGet.mock.calls.length;

    await act(async () => {
      useChatStore.getState().bumpHistoryReset("ses-other");
    });

    // Cross-session signal: the loaded history is untouched and no refetch
    // was issued.
    expect(result.current.messages.length).toBe(2 * PS);
    expect(mockedGet.mock.calls.length).toBe(callsBefore);
  });

  it("a stale refetch captured before a reset cannot resurrect deleted rows", async () => {
    // Race 1: ChatView.runTurn captures `refetch` at the start of a turn and
    // calls it later on done/error/abort. A truncating edit meanwhile fires
    // the history-reset signal. The captured callback must read the CURRENT
    // window from the query cache — not its own render-time snapshot — or it
    // demotes the PRE-truncation window (deleted rows included) back into
    // olderWindows and renders ghosts.
    //
    // Pre-edit: newest ids 2PS+1..3PS, older ids PS+1..2PS. The edit deletes
    // ids PS+1..3PS and re-asks, so the surviving history is ids 1..PS plus
    // two new rows (3PS+1, 3PS+2). Post-reset newest = 3PS+2, 3PS+1, PS..3.
    const postReset = [
      msg(3 * PS + 2),
      msg(3 * PS + 1),
      ...windowOf(PS, PS - 2), // ids PS..3
    ];
    // A valid later append (3PS+3, 3PS+4) slides ids 3 and 4 out of the
    // newest window; the demoted current window must rescue them.
    const slid = [
      msg(3 * PS + 4),
      msg(3 * PS + 3),
      msg(3 * PS + 2),
      msg(3 * PS + 1),
      ...windowOf(PS, PS - 4), // ids PS..5
    ];
    mockedGet
      .mockResolvedValueOnce(windowOf(3 * PS, PS)) // pre-edit newest
      .mockResolvedValueOnce(windowOf(2 * PS, PS)) // older: PS+1..2PS
      .mockResolvedValueOnce(postReset) // reset refetch
      .mockResolvedValueOnce(slid); // stale callback's refetch

    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));
    await act(async () => {
      await result.current.loadOlder();
    });
    expect(result.current.messages.length).toBe(2 * PS);
    expect(result.current.messages.map((m) => m.id)).toContain(PS + 1);

    // Capture the callback from THIS render, before the reset — exactly what
    // an in-flight turn holds.
    const staleRefetch = result.current.refetch;

    await act(async () => {
      useChatStore.getState().bumpHistoryReset("ses-1");
    });
    // Let the reset settle: stale older rows gone, newest window replaced.
    await waitFor(() => expect(result.current.messages.length).toBe(PS));
    expect(result.current.messages.map((m) => m.id)).not.toContain(PS + 1);

    await act(async () => {
      await staleRefetch();
    });

    const ids = result.current.messages.map((m) => m.id);
    // The deleted rows never come back.
    expect(ids).not.toContain(PS + 1);
    expect(ids).not.toContain(2 * PS);
    expect(ids).not.toContain(2 * PS + 1);
    expect(ids).not.toContain(3 * PS);
    // No-regression: the current window was demoted, so history that slid out
    // of the refetched window (ids 3 and 4) is preserved, never lost.
    expect(ids).toContain(3);
    expect(ids).toContain(4);
    expect(result.current.messages[0].id).toBe(3);
    expect(result.current.messages.length).toBe(PS + 2);
    expect(uniqueIds(result.current.messages)).toBe(PS + 2);
  });

  it("a loadOlder page that resolves after a reset is not written into the cleared state", async () => {
    // Race 2: loadOlder fetches a page keyed by a pre-truncation cursor. If a
    // truncating edit resets the history while the fetch is in flight, the
    // page must be dropped (the nonce check) instead of resurrecting rows.
    let resolveOlder!: (v: Message[]) => void;
    const olderPage = new Promise<Message[]>((res) => {
      resolveOlder = res;
    });
    mockedGet
      .mockResolvedValueOnce(windowOf(2 * PS, PS)) // call1: initial newest
      .mockImplementationOnce(() => olderPage) // call2: loadOlder (pending)
      .mockResolvedValueOnce(windowOf(2 * PS, PS)); // call3: reset refetch

    const { result } = renderHook(() => useMessages("ses-1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.messages.length).toBe(PS));

    let loadPromise!: Promise<void>;
    await act(async () => {
      loadPromise = result.current.loadOlder();
    });
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(2));
    expect(result.current.isLoadingOlder).toBe(true);

    // Truncating edit lands while the older page is still in flight.
    await act(async () => {
      useChatStore.getState().bumpHistoryReset("ses-1");
    });
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(3));

    // The pre-truncation page finally resolves.
    await act(async () => {
      resolveOlder(windowOf(PS, PS)); // stale ids 1..PS
      await loadPromise;
    });

    expect(result.current.isLoadingOlder).toBe(false);
    expect(result.current.messages.length).toBe(PS);
    expect(result.current.messages.map((m) => m.id)).not.toContain(1);
  });
});
