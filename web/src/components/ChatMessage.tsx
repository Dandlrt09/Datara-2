import PlotlyChart from "./PlotlyChart";
import DataFrameTable from "./DataFrameTable";

interface ChatMessageProps {
  role: string;
  content: string;
  artifacts?: { kind: string; name: string; payload: unknown }[] | null;
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

export default function ChatMessage({ role, content, artifacts }: ChatMessageProps) {
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