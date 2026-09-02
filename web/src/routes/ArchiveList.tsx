import { useArchives, useArchiveDetail } from "../queries/useArchives";
import { QueryError } from "../components/ErrorCard";

export default function ArchiveList() {
  const { data: archives, isLoading, error, refetch } = useArchives();

  return (
    <div>
      <h1>Archives</h1>
      <QueryError error={error as Error | null} onRetry={refetch}>
        {isLoading && <p>Loading archives...</p>}
        {archives && archives.length === 0 && (
          <p>No archives yet. Chat with your data and archive sessions for later review.</p>
        )}
        {archives && archives.length > 0 && (
          <div>
            {archives.map((a) => (
              <ArchiveCard
                key={a.id}
                archiveId={a.id}
                name={a.name}
                chatSession={a.chat_session}
                createdAt={a.created_at}
              />
            ))}
          </div>
        )}
      </QueryError>
    </div>
  );
}

function ArchiveCard({
  archiveId,
  name,
  chatSession,
  createdAt,
}: {
  archiveId: number;
  name: string;
  chatSession: string;
  createdAt: string;
}) {
  const { data: detail, error, refetch } = useArchiveDetail(archiveId);

  return (
    <div
      style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 16,
        marginBottom: 12,
      }}
    >
      <h3 style={{ margin: "0 0 4px" }}>{name}</h3>
      <p style={{ fontSize: "0.85em", color: "#666", margin: "0 0 8px" }}>
        Session: {chatSession} · Created: {createdAt ? new Date(createdAt).toLocaleDateString() : "—"}
      </p>
      <QueryError error={error as Error | null} onRetry={refetch}>
        {detail?.payload && (
          <details>
            <summary>
              View payload ({detail.payload.messages ? (detail.payload.messages as unknown[]).length : 0} messages)
            </summary>
            <pre style={{ fontSize: "0.85em", maxHeight: 300, overflow: "auto" }}>
              {JSON.stringify(detail.payload, null, 2)}
            </pre>
          </details>
        )}
      </QueryError>
    </div>
  );
}