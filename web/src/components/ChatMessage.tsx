import { useEffect, useRef, useState } from "react";
import { colors, radii, spacing, typography } from "../design/tokens";
import PlotlyChart from "./PlotlyChart";
import DataFrameTable from "./DataFrameTable";

interface ChatMessageProps {
  role: string;
  content: string;
  /** Exact Python the sandbox executed for this turn (assistant messages only). */
  code?: string | null;
  artifacts?: { kind: string; name: string; payload: unknown }[] | null;
  /** LLM token usage for this turn (assistant messages only; null for user
   * messages and rows persisted before usage capture existed). */
  tokensIn?: number | null;
  tokensOut?: number | null;
  costUsd?: number | null;
  /** Server id of this message; required for the user-edit affordance. */
  messageId?: number;
  /** Enables the inline "Editar" affordance. The parent passes it ONLY when a
   * turn can actually start (session present and not streaming). */
  onEdit?: (messageId: number, newText: string) => void;
  /** Enables the "Regenerar" affordance for assistant messages. The parent
   * owns which question is re-run (the last one) and passes this ONLY when a
   * turn can actually start. It takes no arguments on purpose. */
  onRegenerate?: () => void;
  /** True when later user questions exist: editing truncates their turns. */
  hasLaterMessages?: boolean;
}

/** Group an integer with Spanish-style dot thousands separators (1234567 →
 * "1.234.567"). Regex-based so the output is identical across runtimes,
 * independent of their ICU data. */
function formatThousands(n: number): string {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** Format an estimated USD cost with a Spanish decimal comma (0.125 →
 * "0,1250"). Four decimals keep tiny per-turn costs readable. */
function formatCost(usd: number): string {
  return usd.toFixed(4).replace(".", ",");
}

type CopyState = "idle" | "copied" | "error";

/** Code block for the assistant's executed Python: a header row (language
 * label + copy button) above a monospace <pre><code> surface. Long lines
 * scroll horizontally; whitespace is preserved verbatim. */
function CodeBlock({ code }: { code: string }) {
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear the pending feedback timer on unmount so a stale timeout never
  // touches state after the message is gone.
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopyState("copied");
    } catch {
      // Clipboard can fail (permission denied, insecure context): surface a
      // brief error state instead of a false "Copiado".
      setCopyState("error");
    }
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopyState("idle"), 2000);
  };

  return (
    <div
      style={{
        marginTop: spacing.md,
        borderRadius: radii.lg,
        overflow: "hidden",
        border: `1px solid ${colors.codeBorder}`,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: colors.codeHeaderSurface,
          padding: `${spacing.sm}px ${spacing.lg}px`,
        }}
      >
        <span
          style={{
            color: colors.codeHeaderText,
            fontSize: typography.fontSize.xs,
            fontFamily: typography.fontMono,
          }}
        >
          Python
        </span>
        <button
          onClick={handleCopy}
          style={{
            background:
              copyState === "error"
                ? colors.codeButtonSurfaceError
                : colors.codeButtonSurface,
            color: colors.codeButtonText,
            border: "none",
            borderRadius: radii.sm,
            cursor: "pointer",
            fontSize: typography.fontSize.xs,
            padding: `${spacing.xs}px ${spacing.md}px`,
          }}
          title={
            copyState === "error"
              ? "No se pudo copiar el código al portapapeles"
              : undefined
          }
        >
          {copyState === "copied" ? "Copiado" : copyState === "error" ? "Error" : "Copiar"}
        </button>
      </div>
      <pre
        style={{
          margin: 0,
          padding: `${spacing.lg}px ${spacing.xl}px`,
          background: colors.codeSurface,
          color: colors.codeText,
          overflowX: "auto",
          whiteSpace: "pre",
        }}
      >
        <code
          style={{
            fontFamily: typography.fontMono,
            fontSize: typography.fontSize.sm,
          }}
        >
          {code}
        </code>
      </pre>
    </div>
  );
}

/** Render **bold** pairs from model output as real <strong> elements.
 * The prompt forbids Markdown, but flash models leak `**` anyway and the
 * raw asterisks read as noise. Pairs become bold; unmatched `**` stay. */
function renderBold(text: string) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return parts.map((part, i) =>
    i % 2 === 1 ? <strong key={i}>{part}</strong> : part,
  );
}

export default function ChatMessage({
  role,
  content,
  code,
  artifacts,
  tokensIn,
  tokensOut,
  costUsd,
  messageId,
  onEdit,
  onRegenerate,
  hasLaterMessages,
}: ChatMessageProps) {
  const isUser = role === "user";
  // Regenerate is an assistant-only affordance, parent-gated exactly like
  // onEdit: without onRegenerate (not the last answer, or a turn is already
  // streaming) nothing renders.
  const canRegenerate = !isUser && onRegenerate != null;
  // Inline edit state for user questions. Availability is controlled by the
  // parent: without onEdit (e.g. while a turn streams) no Edit affordance is
  // rendered at all.
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const canEdit = isUser && onEdit != null && messageId != null;
  const trimmedDraft = draft.trim();
  // Saving requires a non-empty question that actually changed.
  const canSave = trimmedDraft.length > 0 && trimmedDraft !== content.trim();

  const startEditing = () => {
    setDraft(content);
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setDraft(content);
    setIsEditing(false);
  };

  const saveEditing = () => {
    if (onEdit == null || messageId == null || !canSave) return;
    onEdit(messageId, trimmedDraft);
    setIsEditing(false);
  };

  const handleEditKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      cancelEditing();
    } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      // Plain Enter inserts a newline (multi-line questions); Ctrl/Cmd+Enter
      // submits, mirroring the rename editor's explicit-save pattern.
      e.preventDefault();
      saveEditing();
    }
  };
  // Usage meta line (assistant turns only): total tokens plus the estimated
  // cost when one was computed. User messages and pre-usage rows (null
  // tokens) render nothing at all. A row WITH tokens but a null cost means
  // the model has no price entry — show "costo no disponible" instead of a
  // guessed number.
  const showTokenMeta = !isUser && (tokensIn != null || tokensOut != null);
  const tokenMeta = showTokenMeta
    ? [
        `${formatThousands((tokensIn ?? 0) + (tokensOut ?? 0))} tokens`,
        costUsd == null
          ? "costo no disponible"
          : costUsd > 0
            ? `US$ ${formatCost(costUsd)}`
            : null,
      ]
        .filter((part): part is string => part !== null)
        .join(" · ")
    : null;
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
        marginBottom: spacing.xxl,
      }}
    >
      <div
        style={{
          maxWidth: "80%",
          background: isUser ? colors.accent : colors.surfaceBubble,
          color: isUser ? colors.onAccent : colors.textPrimary,
          borderRadius: radii.xl,
          padding: `${spacing.xl}px ${spacing.xxl}px`,
        }}
      >
        {canEdit && isEditing ? (
          <div>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleEditKeyDown}
              autoFocus
              aria-label="Editar pregunta"
              style={{
                width: "100%",
                boxSizing: "border-box",
                minHeight: 60,
                padding: spacing.md,
                background: colors.onAccent,
                color: colors.textPrimary,
                border: `1px solid ${colors.borderLight}`,
                borderRadius: radii.md,
                fontFamily: "inherit",
                fontSize: "inherit",
                resize: "vertical",
              }}
            />
            {hasLaterMessages && (
              <p
                style={{
                  margin: `${spacing.sm}px 0 0`,
                  color: colors.warningText,
                  fontSize: typography.fontSize.xs,
                }}
              >
                Se van a eliminar las preguntas y respuestas posteriores a esta.
              </p>
            )}
            <div style={{ display: "flex", gap: spacing.sm, marginTop: spacing.sm }}>
              <button
                onClick={saveEditing}
                disabled={!canSave}
                style={{
                  background: colors.surfaceSubtle,
                  color: colors.textPrimary,
                  border: `1px solid ${colors.borderLight}`,
                  borderRadius: radii.sm,
                  padding: `${spacing.xs}px ${spacing.md}px`,
                  cursor: canSave ? "pointer" : "default",
                  fontSize: typography.fontSize.xs,
                }}
              >
                Guardar
              </button>
              <button
                onClick={cancelEditing}
                style={{
                  background: colors.surfaceSubtle,
                  color: colors.textPrimary,
                  border: `1px solid ${colors.borderLight}`,
                  borderRadius: radii.sm,
                  padding: `${spacing.xs}px ${spacing.md}px`,
                  cursor: "pointer",
                  fontSize: typography.fontSize.xs,
                }}
              >
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{renderBold(content)}</p>
        )}
        {canEdit && !isEditing && (
          <button
            onClick={startEditing}
            style={{
              marginTop: spacing.sm,
              background: "transparent",
              border: "none",
              padding: 0,
              cursor: "pointer",
              color: colors.onAccent,
              opacity: 0.85,
              fontSize: typography.fontSize.xs,
              textDecoration: "underline",
            }}
          >
            Editar
          </button>
        )}
        {tokenMeta !== null && (
          <p
            style={{
              margin: `${spacing.sm}px 0 0`,
              color: colors.textMuted,
              fontSize: typography.fontSize.xs,
            }}
          >
            {tokenMeta}
          </p>
        )}
        {/* Executed Python, only for assistant messages with a non-empty
            payload; whitespace-only column values render nothing. */}
        {!isUser && typeof code === "string" && code.trim().length > 0 && (
          <CodeBlock code={code} />
        )}
        {artifacts?.map((art, i) => {
          if (art.kind === "figure") {
            return <PlotlyChart key={i} plotlyJson={art.payload as Record<string, unknown>} />;
          }
          if (art.kind === "text") {
            const p = art.payload as { text?: string };
            return (
              <pre
                key={i}
                style={{
                  marginTop: spacing.md,
                  padding: `${spacing.md}px ${spacing.lg}px`,
                  background: colors.surfaceSubtle,
                  border: `1px solid ${colors.borderLight}`,
                  borderRadius: radii.md,
                  whiteSpace: "pre-wrap",
                  fontFamily: "inherit",
                  fontSize: typography.fontSize.sm,
                  overflowX: "auto",
                }}
              >
                {p.text ?? ""}
              </pre>
            );
          }
          if (art.kind === "table") {
            const p = art.payload as { columns?: string[]; rows?: unknown[][] };
            return (
              <DataFrameTable
                key={i}
                columns={p.columns ?? []}
                rows={p.rows ?? []}
              />
            );
          }
          return null;
        })}
      </div>
      {/* Regenerate lives BELOW the bubble, outside the styled surface, so the
          bubble stays pure content. Assistant-only and parent-gated. */}
      {canRegenerate && (
        <button
          onClick={onRegenerate}
          title="Volver a generar la respuesta"
          aria-label="Volver a generar la respuesta"
          style={{
            marginTop: spacing.sm,
            background: "transparent",
            border: "none",
            padding: 0,
            cursor: "pointer",
            color: colors.textMuted,
            fontSize: typography.fontSize.xs,
            textDecoration: "underline",
          }}
        >
          Regenerar
        </button>
      )}
    </div>
  );
}
