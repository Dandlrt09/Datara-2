import ChatMessage from "./ChatMessage";
import { colors } from "../design/tokens";

interface SnapshotArtifact {
  kind: string;
  name: string;
  payload: unknown;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** Normalize a stored `artifacts` value into what `ChatMessage` expects.
 * Anything malformed is dropped rather than rendered as broken markup. */
function normalizeArtifacts(raw: unknown): SnapshotArtifact[] | null {
  if (!Array.isArray(raw)) return null;
  const artifacts: SnapshotArtifact[] = [];
  for (const entry of raw) {
    const art = asRecord(entry);
    if (!art || typeof art.kind !== "string") continue;
    artifacts.push({
      kind: art.kind,
      name: typeof art.name === "string" ? art.name : "",
      payload: art.payload,
    });
  }
  return artifacts.length > 0 ? artifacts : null;
}

/**
 * Read-only rendering of an archived analysis snapshot.
 *
 * Reuses `ChatMessage` without the interactive callbacks (`onEdit`,
 * `onRegenerate`, `messageId`), so code blocks, tables and figures render but
 * the editing affordances never appear. Malformed or missing payloads degrade
 * to a neutral notice instead of throwing.
 */
export default function ArchiveSnapshot({
  name,
  payload,
}: {
  name: string;
  payload: unknown;
}) {
  const root = asRecord(payload);
  const messages = root && Array.isArray(root.messages) ? root.messages : null;

  const header = (
    <h3 style={{ margin: "0 0 12px", fontSize: 15, color: colors.textPrimary }}>
      {name}
    </h3>
  );

  if (!messages) {
    return (
      <div style={{ marginTop: 12 }}>
        {header}
        <p style={{ margin: 0, color: colors.textMuted }}>
          No se pudo mostrar el análisis
        </p>
      </div>
    );
  }

  return (
    <div style={{ marginTop: 12 }}>
      {header}
      {messages.map((rawMessage, index) => {
        const message = asRecord(rawMessage);
        if (!message) return null;
        const content =
          typeof message.content_text === "string" ? message.content_text : "";
        return (
          <ChatMessage
            key={typeof message.id === "number" ? message.id : index}
            role={typeof message.role === "string" ? message.role : "assistant"}
            content={content}
            code={typeof message.code === "string" ? message.code : null}
            artifacts={normalizeArtifacts(message.artifacts)}
          />
        );
      })}
    </div>
  );
}
