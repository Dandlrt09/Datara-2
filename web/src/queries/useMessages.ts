import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export interface Message {
  id: number;
  role: string;
  content_text: string;
  code?: string | null;
  artifacts?: unknown[] | null;
  model?: string | null;
  created_at?: string | null;
}

/** Page size for chat-history keyset pagination. The backend clamps the
 * `limit` query param to 1..200 and defaults to 50 — this matches it. */
export const MESSAGES_PAGE_SIZE = 50;

/** One raw history window exactly as the API returns it: newest-first
 * (created_at DESC, id DESC — keyset-pagination contract). */
type MessageWindow = Message[];

/** Older windows already loaded for a session, each fetched with
 * `before` = the oldest id of the window above it. Keyed by session id so
 * switching chats can never leak another session's history into the view. */
interface OlderWindowsState {
  sessionId: string;
  windows: MessageWindow[];
  /** Set once a fetch at the bottom of the history returns fewer than
   * MESSAGES_PAGE_SIZE messages — nothing older can exist after that. */
  noMoreOlder: boolean;
}

export interface UseMessagesResult {
  /** Merged history oldest→newest, deduplicated by message id. */
  messages: Message[];
  error: Error | null;
  /** True while a further `before` fetch may still return messages. */
  hasMore: boolean;
  loadOlder: () => Promise<void>;
  isLoadingOlder: boolean;
  loadOlderError: string | null;
  /** Refreshes the newest window while older windows persist. Called after
   * every terminal SSE event; must never lose or duplicate history. */
  refetch: () => Promise<void>;
}

async function fetchWindow(
  sessionId: string,
  before?: number,
): Promise<Message[]> {
  const cursor = before === undefined ? "" : `&before=${before}`;
  return api.get<Message[]>(
    `/api/sessions/${sessionId}/messages?limit=${MESSAGES_PAGE_SIZE}${cursor}`,
  );
}

/**
 * Merge raw newest-first windows into one oldest→newest list — the order the
 * chat renders. The API returns newest-first and the chat renders
 * oldest→newest, so each window is reversed here (without this reversal the
 * assistant answer rendered ABOVE the user's question after every refetch).
 * Duplicates are dropped by id so boundary overlap between windows can never
 * render a message twice.
 */
function mergeWindows(
  newest: MessageWindow | undefined,
  older: MessageWindow[],
): Message[] {
  const windows = [newest, ...older].filter(
    (w): w is MessageWindow => !!w && w.length > 0,
  );
  const seen = new Set<number>();
  const merged: Message[] = [];
  // Oldest window first; within each window, oldest message first (the raw
  // windows are newest-first, hence the reverse iteration).
  for (let i = windows.length - 1; i >= 0; i--) {
    for (let j = windows[i].length - 1; j >= 0; j--) {
      const message = windows[i][j];
      if (seen.has(message.id)) continue;
      seen.add(message.id);
      merged.push(message);
    }
  }
  return merged;
}

/** The bottom-most (oldest) raw window — the one that decides whether the
 * history may continue below the currently loaded messages. */
function bottomWindow(
  newest: MessageWindow | undefined,
  older: MessageWindow[],
): MessageWindow | undefined {
  const windows = [newest, ...older].filter(
    (w): w is MessageWindow => !!w && w.length > 0,
  );
  return windows.length > 0 ? windows[windows.length - 1] : undefined;
}

export function useMessages(sessionId: string | null): UseMessagesResult {
  const [olderState, setOlderState] = useState<OlderWindowsState | null>(null);
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  const [loadOlderError, setLoadOlderError] = useState<string | null>(null);

  // Newest window of the history (raw, newest-first). This is the only page
  // react-query refetches after a terminal SSE event; older windows live in
  // local state and are never invalidated by it.
  const newestQuery = useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => {
      if (!sessionId) return Promise.resolve<Message[]>([]);
      return fetchWindow(sessionId);
    },
    enabled: !!sessionId,
  });

  // Older windows only count for the session they were fetched for; on a
  // session switch the derived value is empty immediately (no effect, no
  // stale flash) until loadOlder stores windows for the new session.
  const olderWindows =
    olderState && olderState.sessionId === sessionId ? olderState.windows : [];
  const noMoreOlder =
    !!olderState && olderState.sessionId === sessionId && olderState.noMoreOlder;

  const messages = useMemo(
    () => mergeWindows(newestQuery.data, olderWindows),
    [newestQuery.data, olderWindows],
  );

  // Keyset heuristic: a bottom window that filled the whole page means older
  // messages MAY exist; a shorter batch means the history ends there. A
  // history whose length is an exact multiple of the page size costs one
  // extra click: the confirming fetch returns empty and the button hides.
  const hasMore = (() => {
    if (noMoreOlder) return false;
    const bottom = bottomWindow(newestQuery.data, olderWindows);
    return !!bottom && bottom.length >= MESSAGES_PAGE_SIZE;
  })();

  const loadOlder = useCallback(async () => {
    if (!sessionId || isLoadingOlder) return;
    const bottom = bottomWindow(newestQuery.data, olderWindows);
    // Nothing to load below an already-exhausted or absent history.
    if (!bottom || bottom.length < MESSAGES_PAGE_SIZE) return;
    setIsLoadingOlder(true);
    setLoadOlderError(null);
    try {
      // Keyset cursor: return messages with id < the oldest loaded id.
      const cursor = bottom[bottom.length - 1].id;
      const batch = await fetchWindow(sessionId, cursor);
      setOlderState((prev) => {
        const windows =
          prev && prev.sessionId === sessionId ? prev.windows : [];
        return {
          sessionId,
          windows: batch.length > 0 ? [...windows, batch] : windows,
          noMoreOlder: batch.length < MESSAGES_PAGE_SIZE,
        };
      });
    } catch (e) {
      setLoadOlderError(
        e instanceof Error ? e.message : "Failed to load older messages",
      );
    } finally {
      setIsLoadingOlder(false);
    }
  }, [sessionId, isLoadingOlder, newestQuery.data, olderWindows]);

  const refetch = useCallback(async () => {
    // Demote the previous newest window into the older windows BEFORE
    // refetching: a turn appends messages at the top, so the fresh newest-50
    // window slides up and the messages that slide out of it would otherwise
    // vanish (they sit below the fresh window and above the first older
    // window). The merge dedupes the overlap between the demoted and the
    // fresh window, so the history never grows a gap after a refetch.
    const snapshot = newestQuery.data;
    if (sessionId && snapshot && snapshot.length >= MESSAGES_PAGE_SIZE) {
      setOlderState((prev) => {
        const same = prev && prev.sessionId === sessionId ? prev : null;
        const kept = (same?.windows ?? []).filter(
          (w) => w[0]?.id !== snapshot[0].id,
        );
        return {
          sessionId,
          windows: [snapshot, ...kept],
          noMoreOlder: same?.noMoreOlder ?? false,
        };
      });
    }
    await newestQuery.refetch();
  }, [sessionId, newestQuery.data, newestQuery.refetch]);

  return {
    messages,
    error: newestQuery.error,
    hasMore,
    loadOlder,
    isLoadingOlder,
    loadOlderError,
    refetch,
  };
}
