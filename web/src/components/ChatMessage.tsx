import { lazy } from "react";
import PlotlyChart from "./PlotlyChart";
import DataFrameTable from "./DataFrameTable";

interface ChatMessageProps {
  role: string;
  content: string;
  artifacts?: { kind: string; name: string; payload: unknown }[] | null;
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
        <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{content}</p>
        {artifacts?.map((art, i) => {
          if (art.kind === "figure") {
            return <PlotlyChart key={i} plotlyJson={art.payload as Record<string, unknown>} />;
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