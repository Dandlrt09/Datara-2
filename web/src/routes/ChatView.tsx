import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useSessions, useCreateSession, useDeleteSession } from "../queries/useSessions";
import { useMessages } from "../queries/useMessages";
import { useChatStore } from "../stores/useChatStore";
import { streamChat } from "../lib/sse";
import ChatMessage from "../components/ChatMessage";
import { QueryError } from "../components/ErrorCard";

export default function ChatView() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const {
    data: sessions,
    error: sessionsError,
    refetch: refetchSessions,
  } = useSessions();
  const { data: messages, refetch: refetchMessages, error: messagesError } =
    useMessages(sessionId ?? null);
  const createSession = useCreateSession();
  const deleteSession = useDeleteSession();

  const store = useChatStore();
  const [question, setQuestion] = useState("");
  const [chatError, setChatError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const isPinnedRef = useRef(true);

  // Set active session
  useEffect(() => {
    store.setActiveSessionId(sessionId ?? null);
  }, [sessionId]);

  // Bottom-pinned scrolling: charts and tables finish rendering AFTER the
  // message list updates (plotly mutates the DOM from its own effect), so a
  // one-shot scrollIntoView on message change lands mid-content. A
  // ResizeObserver re-pins on every content height change; when the user
  // scrolls up to read, the pin releases and we stop yanking the viewport.
  useEffect(() => {
    const scroller = scrollRef.current;
    const content = contentRef.current;
    if (!scroller || !content || typeof ResizeObserver === "undefined") return;
    const repin = () => {
      if (isPinnedRef.current) scroller.scrollTop = scroller.scrollHeight;
    };
    repin();
    const observer = new ResizeObserver(repin);
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  const handleNewSession = async () => {
    const session = await createSession.mutateAsync();
    navigate(`/app/chat/${session.id}`);
  };

  const handleSend = useCallback(async () => {
    if (!sessionId || !question.trim() || store.isStreaming) return;

    const q = question.trim();
    setQuestion("");
    store.clearStreamingText();
    store.setPendingArtifacts(null);
    store.setStreaming(true);
    setChatError(null);

    abortRef.current = new AbortController();

    try {
      await streamChat(
        sessionId,
        q,
        {
          onStatus: (_stage, state) => {
            if (state === "done" || state === "error") {
              store.setStreaming(false);
            }
          },
          onToken: (delta) => store.appendStreamingText(delta),
          onArtifact: (figures, tables, texts) =>
            store.setPendingArtifacts({ figures, tables, texts }),
          onDone: () => {
            store.setStreaming(false);
            // The turn's message is persisted server-side; drop the live
            // streaming state so the refetched list is the single source of
            // truth (otherwise the same answer renders twice: once from the
            // list and once from this block).
            store.clearStreamingText();
            store.setPendingArtifacts(null);
            refetchMessages();
          },
          onError: (type, message) => {
            // Surface WHY the turn failed (bad API key, unknown model,
            // sandbox error...) instead of silently stopping. Error turns
            // also persist the assistant message, so refetch and clear the
            // streaming state for the same no-duplicate reason as onDone.
            store.setStreaming(false);
            store.clearStreamingText();
            store.setPendingArtifacts(null);
            refetchMessages();
            setChatError(message ? `${type}: ${message}` : type);
          },
        },
        abortRef.current.signal
      );
    } catch (e) {
      // streamChat throws on network failures / non-SSE responses. Without
      // this catch, isStreaming stays true forever and the composer bricks.
      setChatError(e instanceof Error ? e.message : "unexpected error sending message");
    } finally {
      store.setStreaming(false);
      abortRef.current = null;
    }
  }, [sessionId, question, store.isStreaming, refetchMessages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ display: "flex", height: "100%" }}>
      {/* Sessions sidebar */}
      <div
        style={{
          width: 260,
          borderRight: "1px solid #ddd",
          padding: 12,
          overflowY: "auto",
        }}
      >
        <button onClick={handleNewSession} style={{ width: "100%", marginBottom: 12 }}>
          + New Chat
        </button>
        <QueryError
          error={sessionsError as Error | null}
          onRetry={refetchSessions}
        >
          {sessions?.map((s) => (
            <div
              key={s.id}
              style={{
                padding: "8px 12px",
                cursor: "pointer",
                background: s.id === sessionId ? "#e3f2fd" : "transparent",
                borderRadius: 6,
                marginBottom: 4,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <Link
                to={`/app/chat/${s.id}`}
                style={{ textDecoration: "none", color: "inherit", flex: 1 }}
              >
                {s.title}
              </Link>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSession.mutate(s.id, {
                    onSuccess: () => {
                      // If we just deleted the open session, leave cleanly
                      // instead of staying on a ghost chat.
                      if (s.id === sessionId) navigate("/app/chat");
                    },
                  });
                }}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#999",
                  fontSize: "1.1em",
                }}
                title="Delete"
              >
                ×
              </button>
            </div>
          ))}
        </QueryError>
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div
          ref={scrollRef}
          onScroll={() => {
            const el = scrollRef.current;
            if (!el) return;
            isPinnedRef.current =
              el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          }}
          style={{ flex: 1, overflowY: "auto", padding: 16 }}
        >
          <div ref={contentRef}>
          {!sessionId && (
            <div style={{ textAlign: "center", marginTop: 80, color: "#999" }}>
              Select a chat or create a new one
            </div>
          )}
          <QueryError
            error={messagesError as Error | null}
            onRetry={refetchMessages}
          >
            {messages?.map((m) => (
              <ChatMessage
                key={m.id}
                role={m.role}
                content={m.content_text}
                artifacts={
                  m.artifacts
                    ? (m.artifacts as {
                        kind: string;
                        name: string;
                        payload: unknown;
                      }[])
                    : null
                }
              />
            ))}
            {/* Streaming message — only while a turn is actually streaming */}
            {store.isStreaming && (store.streamingText || store.pendingArtifacts) && (
              <ChatMessage
                role="assistant"
                content={store.streamingText || "..."}
                artifacts={
                  store.pendingArtifacts
                    ? [
                        ...(store.pendingArtifacts.figures.map((f) => ({
                          kind: "figure" as const,
                          name: (f as Record<string, unknown>).name as string,
                          payload: (f as Record<string, unknown>).plotly ?? f,
                        }))),
                        ...(store.pendingArtifacts.tables.map((t) => ({
                          kind: "table" as const,
                          name: (t as Record<string, unknown>).name as string,
                          payload: t,
                        }))),
                        ...((store.pendingArtifacts.texts ?? []).map((t) => ({
                          kind: "text" as const,
                          name: "stdout",
                          payload: { text: String(t) },
                        }))),
                      ]
                    : null
                }
              />
            )}
          </QueryError>
          </div>
        </div>

        {/* Composer */}
        {chatError && (
          <p role="alert" style={{ color: "#c62828", margin: "0 0 8px" }}>
            {chatError}
          </p>
        )}
        <div
          style={{
            borderTop: "1px solid #ddd",
            padding: 16,
            display: "flex",
            gap: 8,
          }}
        >
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              sessionId
                ? "Ask a question about your data..."
                : "Create or select a chat session first"
            }
            disabled={!sessionId || store.isStreaming}
            style={{ flex: 1, padding: 8, resize: "none", minHeight: 40 }}
            rows={2}
          />
          <button
            onClick={handleSend}
            disabled={!sessionId || !question.trim() || store.isStreaming}
            style={{ padding: "8px 16px" }}
          >
            {store.isStreaming ? "..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}