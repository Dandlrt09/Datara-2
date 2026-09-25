import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link, useLocation } from "react-router-dom";
import { useSessions, useCreateSession, useDeleteSession, useRenameSession } from "../queries/useSessions";
import { useMessages } from "../queries/useMessages";
import { useUploadFile, UploadError } from "../queries/useFiles";
import { useChatStore } from "../stores/useChatStore";
import { useWizardStore } from "../stores/useWizardStore";
import { streamChat } from "../lib/sse";
import { isKnownErrorCode, resolveErrorPresentation } from "../lib/errorCodes";
import ChatMessage from "../components/ChatMessage";
import { ErrorCard, QueryError } from "../components/ErrorCard";
import { SheetPicker } from "../components/SheetPicker";

// Composer attach control: mirrors the server's accepted formats
// (server/api/routers/files.py ``_SUPPORTED_EXTENSIONS``). ``.tab`` is NOT
// accepted here because the server rejects it.
const ACCEPTED_UPLOAD_EXTENSIONS = [".csv", ".tsv", ".xlsx", ".json"];

export default function ChatView() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const {
    data: sessions,
    error: sessionsError,
    refetch: refetchSessions,
  } = useSessions();
  const {
    messages,
    refetch: refetchMessages,
    error: messagesError,
    hasMore,
    loadOlder,
    isLoadingOlder,
    loadOlderError,
  } = useMessages(sessionId ?? null);
  const createSession = useCreateSession();
  const deleteSession = useDeleteSession();
  const renameSession = useRenameSession();

  // Inline rename editor state: which sidebar row is being renamed and the
  // value currently in its input. Null renamingId = no row in edit mode.
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");

  const store = useChatStore();
  const wizardStore = useWizardStore();
  const [question, setQuestion] = useState("");
  const [chatError, setChatError] = useState<{
    type: string;
    code: string | null;
    message: string;
  } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Last question sent in this session — the Retry button re-runs it.
  const lastQuestionRef = useRef("");
  // Set when THIS tab's own turn settles (terminal event or abort). The
  // cross-tab stream-end effect consumes it so this tab never refetches twice
  // for a turn it already resynced in onDone/onError/finally.
  const ownTurnSettledRef = useRef(false);
  // Composer attach control: in-flight upload + its abort handle + its copy.
  const uploadFileMut = useUploadFile();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadAbortRef = useRef<AbortController | null>(null);
  // Distinguishes the user pressing "Cancelar" from the abort fired on
  // session change/unmount: only the former may report "Carga cancelada.",
  // otherwise that copy would leak into the session the user just opened.
  const uploadCanceledByUserRef = useRef(false);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [attachNotice, setAttachNotice] = useState<string | null>(null);
  // Set after attaching a multi-sheet workbook so the picker can be shown
  // inline before the first sheet silently becomes the analyzed one.
  const [attachSheets, setAttachSheets] = useState<{
    fileId: number;
    sheets: string[];
    sheetName: string | null;
  } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const isPinnedRef = useRef(true);
  // Ref to track if we've consumed the suggested question from location.state
  const consumedSuggestedQuestionRef = useRef(false);
  // Viewport restore after "load older": captured before the fetch, applied
  // once the prepended messages commit (see the effect below).
  const pendingScrollRestoreRef = useRef<{
    sessionId: string | undefined;
    prevHeight: number;
    prevTop: number;
  } | null>(null);

  // Set active session and drop any banner from the previous session: a
  // failure that happened in one chat must never leak into another.
  useEffect(() => {
    store.setActiveSessionId(sessionId ?? null);
    setChatError(null);
    // An attach failure/notice belongs to the session it happened in — never
    // leak it into the next chat.
    setAttachError(null);
    setAttachNotice(null);
    setAttachSheets(null);
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

  // "Load older" grows the content ABOVE the viewport. After the prepended
  // messages commit, compensate the scroll position by the height delta so
  // the user keeps reading exactly where they were; the bottom pin was
  // released when the button was clicked, so the ResizeObserver cannot yank
  // the viewport to the bottom during this window.
  useEffect(() => {
    const pending = pendingScrollRestoreRef.current;
    if (!pending || pending.sessionId !== sessionId) return;
    pendingScrollRestoreRef.current = null;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight - pending.prevHeight + pending.prevTop;
  }, [messages, sessionId]);

  const handleNewSession = async () => {
    const session = await createSession.mutateAsync();
    navigate(`/app/chat/${session.id}`);
  };

  const startRename = (id: string, title: string) => {
    setRenamingId(id);
    setRenameTitle(title);
  };

  const cancelRename = () => {
    setRenamingId(null);
    setRenameTitle("");
  };

  const submitRename = () => {
    if (!renamingId) return;
    // The server trims and rejects empty titles (422); guard here so the
    // button never fires a doomed request.
    const title = renameTitle.trim();
    if (!title) return;
    renameSession.mutate(
      { id: renamingId, title },
      { onSuccess: () => cancelRename() },
    );
  };

  const runTurn = useCallback(
    async (q: string, retry: boolean, editMessageId?: number) => {
      if (!sessionId || !q.trim() || store.isStreaming) return;

      if (!retry) setQuestion("");
      store.clearStreamingText();
      store.setPendingArtifacts(null);
      store.setStreaming(true);
      setChatError(null);
      lastQuestionRef.current = q;

      abortRef.current = new AbortController();

      // Set true only by terminal SSE events (done/error). Any other way
      // the stream ends — user abort via Detener, dropped connection,
      // thrown fetch — leaves it false, so the finally block resyncs the
      // history from the DB (persist-then-emit) and drops streaming
      // residue from the global store.
      let turnSettled = false;

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
              turnSettled = true;
              ownTurnSettledRef.current = true;
              store.setStreaming(false);
              // The turn's message is persisted server-side; drop the live
              // streaming state so the refetched list is the single source of
              // truth (otherwise the same answer renders twice: once from the
              // list and once from this block).
              store.clearStreamingText();
              store.setPendingArtifacts(null);
              refetchMessages();
            },
            onError: (type, code, message) => {
              // Surface WHY the turn failed (bad API key, unknown model,
              // sandbox error...) instead of silently stopping. Failed turns
              // persist nothing server-side, so the history keeps just the
              // question and the Retry button re-runs it.
              turnSettled = true;
              ownTurnSettledRef.current = true;
              store.setStreaming(false);
              store.clearStreamingText();
              store.setPendingArtifacts(null);
              refetchMessages();
              setChatError({ type, code, message });
            },
          },
          abortRef.current.signal,
          { retry, editMessageId }
        );
      } catch (e) {
        // streamChat throws on network failures / non-SSE responses. Without
        // this catch, isStreaming stays true forever and the composer bricks.
        setChatError({
          type: "connection_error",
          code: null,
          message: e instanceof Error ? e.message : "unexpected error sending message",
        });
      } finally {
        store.setStreaming(false);
        abortRef.current = null;
        // Any way this tab's own turn ends marks the settle so the cross-tab
        // effect does not double-fetch when the sessions cache flips to false.
        ownTurnSettledRef.current = true;
        if (!turnSettled) {
          // Aborted or silently-ended stream: the server only persisted the
          // question (before the stream started), so resync the history and
          // clear the live streaming residue. The Retry affordance lights up
          // from the trailing user message in the refetched list.
          store.clearStreamingText();
          store.setPendingArtifacts(null);
          void refetchMessages();
        }
      }
    },
    [sessionId, store.isStreaming, refetchMessages]
  );

  const handleSend = useCallback(() => {
    const q = question.trim();
    if (!q) return;
    void runTurn(q, false);
  }, [question, runTurn]);

  const handleStop = useCallback(() => {
    // Aborting makes streamChat return without surfacing an error
    // (AbortError is swallowed there); runTurn's finally then drops the
    // streaming residue and resyncs the persisted history.
    abortRef.current?.abort();
  }, []);

  const handleAttachFile = useCallback(
    async (file: File) => {
      if (!sessionId || store.isStreaming || uploadFileMut.isPending) return;

      const trimmedName = file.name.trim();
      const dot = trimmedName.lastIndexOf(".");
      const ext = dot >= 0 ? trimmedName.slice(dot).toLowerCase() : "";
      if (!ACCEPTED_UPLOAD_EXTENSIONS.includes(ext)) {
        // No extension must not print an empty parenthesis.
        const shownExt = ext || "sin extensión";
        setAttachError(
          `Formato no soportado (${shownExt}). Usá CSV, TSV, XLSX o JSON.`,
        );
        return;
      }

      setAttachError(null);
      setAttachNotice(null);
      setAttachSheets(null);
      uploadCanceledByUserRef.current = false;
      const controller = new AbortController();
      uploadAbortRef.current = controller;
      try {
        const result = await uploadFileMut.mutateAsync({
          sessionId,
          file,
          signal: controller.signal,
        });
        setAttachNotice(`${file.name} adjuntado a esta sesión.`);
        if (result?.sheets && result.sheets.length > 1) {
          setAttachSheets({
            fileId: result.id,
            sheets: result.sheets,
            sheetName: result.sheet_name ?? null,
          });
        }
      } catch (e) {
        if ((e as Error)?.name === "AbortError") {
          // Silent when the abort came from leaving the session: the new
          // session must not inherit a message about the previous upload.
          if (uploadCanceledByUserRef.current) setAttachError("Carga cancelada.");
        } else if (e instanceof UploadError && e.status === 409) {
          setAttachError(
            "Ya hay un archivo con ese nombre en esta sesión. Borralo antes de volver a subirlo.",
          );
        } else if (e instanceof UploadError && e.status === 400) {
          setAttachError(
            "No se pudo leer el archivo. Verificá el formato y el contenido.",
          );
        } else {
          setAttachError("No se pudo adjuntar el archivo. Reintentá.");
        }
      } finally {
        uploadAbortRef.current = null;
      }
    },
    [sessionId, store.isStreaming, uploadFileMut],
  );

  const handleLoadOlder = useCallback(() => {
    const el = scrollRef.current;
    if (el) {
      pendingScrollRestoreRef.current = {
        sessionId,
        prevHeight: el.scrollHeight,
        prevTop: el.scrollTop,
      };
      // Loading prepends content above the viewport: release the bottom pin
      // so it cannot fight the position restore while the DOM grows.
      isPinnedRef.current = false;
    }
    void loadOlder();
  }, [sessionId, loadOlder]);

  // Abort any in-flight turn when leaving the session — on unmount or when
  // navigating to another chat — so the stream never keeps running in the
  // background and the global streaming state cannot bleed into the next
  // session's view. runTurn's finally clears the store state afterwards.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      // An upload must not outlive the session view either.
      uploadAbortRef.current?.abort();
    };
  }, [sessionId]);

  // Cross-tab streaming state for the OPEN session, derived from the sessions
  // cache that also drives the sidebar dot. Unknown/not-found degrades to
  // false so the Retry formula below keeps today's behavior exactly.
  const openSession = sessions?.find((s) => s.id === sessionId);
  const openSessionIsStreaming = openSession?.is_streaming === true;

  // When the open session's cross-tab stream ends, pull the assistant answer
  // into this observing tab. The previous-value ref is seeded with the CURRENT
  // value so mounting while is_streaming is already true never fires a fetch.
  const prevOpenStreamingRef = useRef(openSessionIsStreaming);
  useEffect(() => {
    const wasStreaming = prevOpenStreamingRef.current;
    prevOpenStreamingRef.current = openSessionIsStreaming;
    if (!wasStreaming && openSessionIsStreaming) {
      // A new stream began; a previous own-turn settle no longer applies.
      ownTurnSettledRef.current = false;
      return;
    }
    if (wasStreaming && !openSessionIsStreaming) {
      // The tab that ran the turn already resynced in onDone/onError/finally.
      if (ownTurnSettledRef.current) {
        ownTurnSettledRef.current = false;
        return;
      }
      // useMessages.refetch() demotes the previous newest window before
      // refetching, so the sliding window cannot drop history (a bare
      // invalidate would bypass that and leave a gap in long sessions).
      void refetchMessages();
    }
  }, [openSessionIsStreaming, refetchMessages]);

  // A trailing user message (no assistant reply after it) is a persisted
  // failed/aborted turn — keep the Retry affordance available across
  // navigation and reloads instead of tying it to ephemeral error state. A
  // cross-tab stream in flight suppresses it: the turn is alive elsewhere, so
  // offering Retry would contradict the sidebar dot for the same session.
  const lastMessage = messages.length > 0 ? messages[messages.length - 1] : undefined;
  const retryAvailable =
    !!sessionId &&
    !store.isStreaming &&
    !openSessionIsStreaming &&
    lastMessage?.role === "user";

  const handleRetryTurn = useCallback(() => {
    // Prefer the persisted history: the failed turn's question survives
    // navigation and reloads, unlike component state (chatError /
    // lastQuestionRef die on remount — that's how B4 red happened).
    const q =
      lastQuestionRef.current ||
      (lastMessage?.role === "user" ? lastMessage.content_text : "");
    if (q) void runTurn(q, true);
  }, [runTurn, lastMessage]);

  // Edit question (truncate): the server deletes this message and every later
  // turn, then re-asks the edited text as a normal turn.
  const handleEditMessage = useCallback(
    (messageId: number, text: string) => {
      if (!sessionId || store.isStreaming) return;
      void runTurn(text, false, messageId);
    },
    [sessionId, store.isStreaming, runTurn],
  );

  // Regenerate: re-run the LAST user question through the edit path with the
  // SAME text. The server truncates that turn (including the previous answer)
  // before re-asking, so the model starts clean. Deliberately NOT retry, which
  // keeps the old answer in context and tends to repeat it.
  const handleRegenerate = useCallback(() => {
    if (!sessionId || store.isStreaming) return;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        void runTurn(messages[i].content_text, false, messages[i].id);
        return;
      }
    }
  }, [sessionId, store.isStreaming, messages, runTurn]);

  // Last user question in the loaded history. An edit can only start a turn
  // when the session is present and neither this tab nor another tab is
  // streaming it — the same states that disable the composer.
  const lastUserId = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") return messages[i].id;
    }
    return undefined;
  })();
  const canEditMessage =
    !!sessionId && !store.isStreaming && !openSessionIsStreaming;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Typed error presentation: the taxonomy code selects the ErrorCard
  // variant and action. Missing/unknown codes degrade to today's verbatim
  // `${type}: ${message}` banner format (safe fallback, never crashes).
  const errorPresentation = chatError
    ? resolveErrorPresentation(chatError.code)
    : null;
  const errorMessage = chatError
    ? isKnownErrorCode(chatError.code)
      ? errorPresentation?.action === "go-settings"
        ? // Auth failures: point the user at the API-key configuration.
          `${chatError.message} Configura tu API key en Ajustes y vuelve a intentarlo.`
        : chatError.message
      : `${chatError.type}: ${chatError.message}`
    : undefined;

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
              {renamingId === s.id ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    submitRename();
                  }}
                  style={{ display: "flex", gap: 4, flex: 1, alignItems: "center" }}
                >
                  <input
                    value={renameTitle}
                    onChange={(e) => setRenameTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") cancelRename();
                    }}
                    autoFocus
                    maxLength={200}
                    aria-label="Nuevo nombre de la sesión"
                    style={{ flex: 1, minWidth: 0, padding: "2px 6px", fontSize: "inherit" }}
                  />
                  <button type="submit" disabled={!renameTitle.trim() || renameSession.isPending}>
                    Guardar
                  </button>
                  <button type="button" onClick={cancelRename}>
                    Cancelar
                  </button>
                </form>
              ) : (
                <>
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
                      startRename(s.id, s.title);
                    }}
                    style={{
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      color: "#999",
                      fontSize: "1.1em",
                    }}
                    title="Renombrar"
                    aria-label="Renombrar"
                  >
                    ✎
                  </button>
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
                </>
              )}
            </div>
          ))}
        </QueryError>
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div
          ref={scrollRef}
          data-testid="chat-scroll"
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
            {hasMore && (
              <div style={{ textAlign: "center", marginBottom: 12 }}>
                {loadOlderError && (
                  <p
                    role="alert"
                    style={{ color: "#c62828", margin: "0 0 8px", fontSize: "0.9em" }}
                  >
                    No se pudieron cargar los mensajes anteriores.
                  </p>
                )}
                <button
                  onClick={handleLoadOlder}
                  disabled={isLoadingOlder}
                  style={{ padding: "6px 14px" }}
                >
                  {isLoadingOlder ? "Cargando..." : "Cargar mensajes anteriores"}
                </button>
              </div>
            )}
            {messages.map((m) => (
              <ChatMessage
                key={m.id}
                role={m.role}
                content={m.content_text}
                code={m.code}
                messageId={m.role === "user" ? m.id : undefined}
                onEdit={
                  m.role === "user" && canEditMessage
                    ? handleEditMessage
                    : undefined
                }
                onRegenerate={
                  m.role === "assistant" &&
                  m.id === lastMessage?.id &&
                  canEditMessage
                    ? handleRegenerate
                    : undefined
                }
                hasLaterMessages={
                  m.role === "user" ? m.id !== lastUserId : undefined
                }
                tokensIn={m.tokens_in}
                tokensOut={m.tokens_out}
                costUsd={m.cost_usd}
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
            {/* Streaming message — only while a turn is actually streaming.
                No code prop on purpose: the executed Python is only persisted
                with the finished message (persist-then-emit); the refetched
                list renders it right after done. */}
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
        {chatError && errorPresentation && (
          <ErrorCard
            variant={errorPresentation.variant}
            title={errorPresentation.title}
            message={errorMessage}
            actionLabel={errorPresentation.actionLabel}
            onRetry={
              errorPresentation.action === "retry-turn"
                ? handleRetryTurn
                : errorPresentation.action === "go-settings"
                  ? () => navigate("/app/settings")
                  : undefined
            }
          />
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
        {(uploadFileMut.isPending || attachError || attachNotice) && (
          <div style={{ marginBottom: 8 }}>
            {uploadFileMut.isPending ? (
              <div role="status" style={{ color: "#555" }}>
                <span style={{ marginRight: 8 }}>Subiendo archivo…</span>
                <button
                  onClick={() => {
                    uploadCanceledByUserRef.current = true;
                    uploadAbortRef.current?.abort();
                  }}
                >
                  Cancelar
                </button>
              </div>
            ) : attachError ? (
              <p role="alert" style={{ color: "#c62828", margin: 0 }}>
                {attachError}
              </p>
            ) : (
              <p role="status" style={{ color: "#2e7d32", margin: 0 }}>
                {attachNotice}
              </p>
            )}
          </div>
        )}
        {attachSheets && (
          <SheetPicker
            fileId={attachSheets.fileId}
            sheets={attachSheets.sheets}
            currentSheet={attachSheets.sheetName}
            onSelected={() => setAttachSheets(null)}
          />
        )}
        <div
          style={{
            borderTop: "1px solid #ddd",
            padding: 16,
            display: "flex",
            gap: 8,
          }}
        >
          <input
            type="file"
            ref={fileInputRef}
            accept=".csv,.tsv,.xlsx,.json"
            aria-label="Adjuntar archivo"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              // Reset so re-selecting the same file fires `change` again.
              e.target.value = "";
              if (file) void handleAttachFile(file);
            }}
          />
          <button
            type="button"
            aria-label="Adjuntar archivo"
            onClick={() => {
              setAttachError(null);
              fileInputRef.current?.click();
            }}
            disabled={!sessionId || store.isStreaming || uploadFileMut.isPending}
            title={
              !sessionId
                ? "Creá o seleccioná una sesión para adjuntar archivos"
                : "Adjuntar archivo (CSV, TSV, XLSX o JSON)"
            }
            style={{ padding: "8px 12px" }}
          >
            {uploadFileMut.isPending ? "…" : "Adjuntar"}
          </button>
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
          {/* While a turn is streaming the send slot becomes the stop
              button — they can never act at the same time. */}
          {store.isStreaming ? (
            <button
              onClick={handleStop}
              style={{ padding: "8px 16px" }}
              title="Detener la respuesta en curso"
            >
              Detener
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!sessionId || !question.trim()}
              style={{ padding: "8px 16px" }}
            >
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
