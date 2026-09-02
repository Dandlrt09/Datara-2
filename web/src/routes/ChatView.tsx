import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useSessions, useCreateSession, useDeleteSession } from "../queries/useSessions";
import { useMessages } from "../queries/useMessages";
import { useChatStore } from "../stores/useChatStore";
import { streamChat } from "../lib/sse";
import ChatMessage from "../components/ChatMessage";

export default function ChatView() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { data: sessions } = useSessions();
  const { data: messages, refetch: refetchMessages } = useMessages(sessionId ?? null);
  const createSession = useCreateSession();
  const deleteSession = useDeleteSession();

  const store = useChatStore();
  const [question, setQuestion] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Set active session
  useEffect(() => {
    store.setActiveSessionId(sessionId ?? null);
  }, [sessionId]);

  // Scroll to bottom on new messages or streaming
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, store.streamingText]);

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

    abortRef.current = new AbortController();

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
        onArtifact: (figures, tables) => store.setPendingArtifacts({ figures, tables }),
        onDone: () => {
          store.setStreaming(false);
          refetchMessages();
        },
        onError: () => {
          store.setStreaming(false);
        },
      },
      abortRef.current.signal
    );

    abortRef.current = null;
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
      <div style={{ width: 260, borderRight: "1px solid #ddd", padding: 12, overflowY: "auto" }}>
        <button onClick={handleNewSession} style={{ width: "100%", marginBottom: 12 }}>
          + New Chat
        </button>
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
            <Link to={`/app/chat/${s.id}`} style={{ textDecoration: "none", color: "inherit", flex: 1 }}>
              {s.title}
            </Link>
            <button
              onClick={(e) => {
                e.stopPropagation();
                deleteSession.mutate(s.id);
                if (s.id === sessionId) navigate("/app/chat");
              }}
              style={{ background: "none", border: "none", cursor: "pointer", color: "#999" }}
              title="Delete"
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {!sessionId && (
            <div style={{ textAlign: "center", marginTop: 80, color: "#999" }}>
              Select a chat or create a new one
            </div>
          )}
          {messages?.map((m) => (
            <ChatMessage
              key={m.id}
              role={m.role}
              content={m.content_text}
              artifacts={
                m.artifacts
                  ? (m.artifacts as { kind: string; name: string; payload: unknown }[])
                  : null
              }
            />
          ))}
          {/* Streaming message */}
          {(store.streamingText || store.pendingArtifacts) && (
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
                    ]
                  : null
              }
            />
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Composer */}
        <div style={{ borderTop: "1px solid #ddd", padding: 16, display: "flex", gap: 8 }}>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your data..."
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