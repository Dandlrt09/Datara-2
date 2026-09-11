import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link, useLocation } from "react-router-dom";
import { useSessions, useCreateSession, useDeleteSession } from "../queries/useSessions";
import { useMessages } from "../queries/useMessages";
import { useChatStore } from "../stores/useChatStore";
import { useWizardStore } from "../stores/useWizardStore";
import { streamChat } from "../lib/sse";
import ChatMessage from "../components/ChatMessage";
import { QueryError } from "../components/ErrorCard";

export default function ChatView() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
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
  const wizardStore = useWizardStore();
  const [question, setQuestion] = useState("");
  const [chatError, setChatError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Last question sent in this session — the Retry button re-runs it.
  const lastQuestionRef = useRef("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const isPinnedRef = useRef(true);
  // Ref to track if we've consumed the suggested question from location.state
  const consumedSuggestedQuestionRef = useRef(false);

  // Set active session
  useEffect(() => {
    store.setActiveSessionId(sessionId ?? null);
  }, [sessionId]);

  // Consume suggested question from location.state (one-shot)
  useEffect(() => {
    const suggestedQuestion = (location.state as { suggestedQuestion?: string } | null)?.suggestedQuestion;
    if (suggestedQuestion && !consumedSuggestedQuestionRef.current) {
      setQuestion(suggestedQuestion);
      consumedSuggestedQuestionRef.current = true;
    }
  }, [location.state]);

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

  const runTurn = useCallback(
    async (q: string, retry: boolean) => {
      if (!sessionId || !q.trim() || store.isStreaming) return;

      if (!retry) setQuestion("");
      store.clearStreamingText();
      store.setPendingArtifacts(null);
      store.setStreaming(true);
      setChatError(null);
      lastQuestionRef.current = q;

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
              // sandbox error...) instead of silently stopping. Failed turns
              // persist nothing server-side, so the history keeps just the
              // question and the Retry button re-runs it.
              store.setStreaming(false);
              store.clearStreamingText();
              store.setPendingArtifacts(null);
              refetchMessages();
              setChatError(message ? `${type}: ${message}` : type);
            },
          },
          abortRef.current.signal,
          retry
        );
      } catch (e) {
        // streamChat throws on network failures / non-SSE responses. Without
        // this catch, isStreaming stays true forever and the composer bricks.
        setChatError(e instanceof Error ? e.message : "unexpected error sending message");
      } finally {
        store.setStreaming(false);
        abortRef.current = null;
      }
    },
    [sessionId, store.isStreaming, refetchMessages]
  );

  const handleSend = useCallback(() => {
    const q = question.trim();
    if (!q) return;
    void runTurn(q, false);
  }, [question, runTurn]);

  // A trailing user message (no assistant reply after it) is a persisted
  // failed/aborted turn — keep the Retry affordance available across
  // navigation and reloads instead of tying it to ephemeral error state.
  const lastMessage = messages?.[messages.length - 1];
  const retryAvailable =
    !!sessionId && !store.isStreaming && lastMessage?.role === "user";

  const handleRetryTurn = useCallback(() => {
    // Prefer the persisted history: the failed turn's question survives
    // navigation and reloads, unlike component state (chatError /
    // lastQuestionRef die on remount — that's how B4 red happened).
    const q =
      lastQuestionRef.current ||
      (lastMessage?.role === "user" ? lastMessage.content_text : "");
    if (q) void runTurn(q, true);
  }, [runTurn, lastMessage]);

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
                style={{ textDecoration: "none", color: "inherit", flex: 1, display: "flex", alignItems: "center", gap: 6 }}
              >
                <span style={{ flex: 1 }}>{s.title}</span>
                {s.is_streaming && (
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: "#4caf50",
                      display: "inline-block",
                      animation: "pulse 1.5s ease-in-out infinite",
                      flexShrink: 0,
                    }}
                    title="Streaming in progress"
                  />
                )}
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
              <p>Select a chat or create a new one</p>
              <button
                onClick={() => wizardStore.openWizard(true)}
                style={{
                  marginTop: "16px",
                  padding: "10px 20px",
                  backgroundColor: "#007bff",
                  color: "white",
                  border: "none",
                  borderRadius: "4px",
                  cursor: "pointer",
                  fontSize: "1em",
                }}
              >
                Start first-run wizard
              </button>
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
            {chatError}{" "}
            {!store.isStreaming && sessionId && (
              <button
                onClick={handleRetryTurn}
                title="Re-run the failed turn (does not duplicate the question)"
              >
                Retry
              </button>
            )}
          </p>
        )}
        {!chatError && retryAvailable && (
          <div style={{ marginBottom: 8 }}>
            <span style={{ color: "#555", marginRight: 8 }}>
              El último turno quedó sin respuesta.
            </span>
            <button
              onClick={handleRetryTurn}
              title="Re-run the failed turn (does not duplicate the question)"
            >
              Retry
            </button>
          </div>
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