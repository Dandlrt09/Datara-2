import { useEffect, useRef, useState } from "react";
import PlotlyChart from "./PlotlyChart";
import DataFrameTable from "./DataFrameTable";

interface ChatMessageProps {
  role: string;
  content: string;
  /** Exact Python the sandbox executed for this turn (assistant messages only). */
  code?: string | null;
  artifacts?: { kind: string; name: string; payload: unknown }[] | null;
}

const CODE_FONT = '"JetBrains Mono", ui-monospace, monospace';

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
        marginTop: 8,
        borderRadius: 8,
        overflow: "hidden",
        border: "1px solid #444",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#2d2d2d",
          padding: "4px 10px",
        }}
      >
        <span style={{ color: "#bbb", fontSize: "0.75em", fontFamily: CODE_FONT }}>
          Python
        </span>
        <button
          onClick={handleCopy}
          style={{
            background: copyState === "error" ? "#5a2d2d" : "#3a3a3a",
            color: "#ddd",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
            fontSize: "0.75em",
            padding: "2px 8px",
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
          padding: "10px 12px",
          background: "#1e1e1e",
          color: "#e8e8e8",
          overflowX: "auto",
          whiteSpace: "pre",
        }}
      >
        <code style={{ fontFamily: CODE_FONT, fontSize: "0.85em" }}>{code}</code>
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

export default function ChatMessage({ role, content, code, artifacts }: ChatMessageProps) {
  const isUser = role === "user";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 16,
      }}
    >
      <div
        style={{
          maxWidth: "80%",
          background: isUser ? "#007bff" : "#f0f0f0",
          color: isUser ? "#fff" : "#333",
          borderRadius: 12,
          padding: "12px 16px",
        }}
      >
        <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{renderBold(content)}</p>
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
                  marginTop: 8,
                  padding: "8px 10px",
                  background: "#fafafa",
                  border: "1px solid #e0e0e0",
                  borderRadius: 6,
                  whiteSpace: "pre-wrap",
                  fontFamily: "inherit",
                  fontSize: "0.85em",
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
    </div>
  );
}