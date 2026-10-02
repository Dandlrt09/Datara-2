import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  useArchives,
  useArchiveDetail,
  type Archive,
  type ArchiveDetail,
} from "../queries/useArchives";
import { ErrorCard } from "../components/ErrorCard";
import { colors } from "../design/tokens";
import { formatNumberEs } from "../lib/formatNumbers";
import { formatRelativeTimeEs } from "../lib/relativeTime";

/** Case- and accent-insensitive key for the client-side name search. */
function normalizeForSearch(text: string): string {
  return text
    .toLocaleLowerCase("es")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

const chipStyle = {
  padding: "2px 6px",
  fontSize: "0.75em",
  borderRadius: 4,
  background: "#fff3cd",
  color: "#856404",
  border: "1px solid #ffeeba",
  fontFamily: "inherit",
} as const;

// Secondary, visually subdued chip for the "+N more files" indicator.
const mutedChipStyle = {
  padding: "2px 6px",
  fontSize: "0.75em",
  borderRadius: 4,
  background: "#f5f5f5",
  color: colors.textMuted,
  border: `1px solid ${colors.borderLight}`,
  fontFamily: "inherit",
} as const;

const inertActionStyle = {
  padding: 0,
  border: "none",
  background: "none",
  color: colors.textMuted,
  fontSize: 13,
  cursor: "not-allowed",
} as const;

const detailToggleStyle = {
  padding: "4px 10px",
  fontSize: 12,
  borderRadius: 6,
  border: `1px solid ${colors.borderLight}`,
  background: "#fff",
  color: colors.textMuted,
  cursor: "pointer",
} as const;

const detailErrorTitle = "No se pudo cargar el detalle";
const listErrorTitle = "No se pudieron cargar los análisis";

export default function ArchiveList() {
  const { data: archives, isLoading, error, refetch } = useArchives();
  const [search, setSearch] = useState("");
  const [newestFirst, setNewestFirst] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // Exactly ONE detail fetch for the whole list. `null` disables the query
  // until a card is expanded, which kills the previous per-row N+1.
  const {
    data: detail,
    error: detailError,
    refetch: refetchDetail,
  } = useArchiveDetail(expandedId);

  const visibleArchives = useMemo(() => {
    const list = archives ?? [];
    const query = normalizeForSearch(search.trim());
    const filtered = query
      ? list.filter((a) => normalizeForSearch(a.name).includes(query))
      : list;
    // The endpoint already returns DESC; sorting here keeps the order control
    // honest and deterministic for both directions.
    return [...filtered].sort((a, b) => {
      const cmp = String(a.created_at).localeCompare(String(b.created_at));
      return newestFirst ? -cmp : cmp;
    });
  }, [archives, search, newestFirst]);

  const hasArchives = !!archives && archives.length > 0;

  return (
    <div>
      <h1 style={{ margin: "0 0 16px", color: colors.textPrimary }}>Análisis</h1>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 16,
        }}
      >
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar análisis…"
          aria-label="Buscar análisis"
          style={{
            flex: 1,
            maxWidth: 420,
            padding: "8px 12px",
            fontSize: 14,
            borderRadius: 8,
            border: `1px solid ${colors.borderLight}`,
            background: "#fff",
            color: colors.textPrimary,
          }}
        />
        <button
          type="button"
          onClick={() => setNewestFirst((v) => !v)}
          style={{
            padding: "8px 12px",
            fontSize: 13,
            borderRadius: 8,
            border: `1px solid ${colors.borderLight}`,
            background: "#fff",
            color: colors.textMuted,
            cursor: "pointer",
          }}
        >
          {newestFirst ? "Más recientes" : "Más antiguos"}
        </button>
      </div>

      {error && (
        <ErrorCard
          title={listErrorTitle}
          error={error}
          onRetry={refetch}
          actionLabel="Reintentar"
        />
      )}

      {isLoading && !error && (
        <p style={{ color: colors.textMuted }}>Cargando análisis…</p>
      )}

      {!error && archives && archives.length === 0 && (
        <div
          style={{
            padding: 24,
            borderRadius: 8,
            border: `1px solid ${colors.borderLight}`,
            textAlign: "center",
          }}
        >
          <p style={{ margin: "0 0 12px", color: colors.textPrimary }}>
            Sube un archivo y pide un análisis
          </p>
          <Link to="/app/chat">Ir al chat</Link>
        </div>
      )}

      {hasArchives && visibleArchives.length === 0 && (
        <p style={{ color: colors.textMuted }}>No se encontraron análisis</p>
      )}

      {hasArchives && (
        <div>
          {visibleArchives.map((a) => {
            const isExpanded = expandedId === a.id;
            return (
              <ArchiveCard
                key={a.id}
                archive={a}
                expanded={isExpanded}
                detail={isExpanded ? detail : undefined}
                detailError={isExpanded ? (detailError as Error | null) : null}
                onToggleDetail={() => setExpandedId(isExpanded ? null : a.id)}
                onRetryDetail={refetchDetail}
              />
            );
          })}
        </div>
      )}

      {hasArchives && (
        <p
          style={{
            marginTop: 16,
            fontSize: 13,
            lineHeight: 1.4,
            color: colors.textMuted,
          }}
        >
          Un análisis guarda la conversación, el código y los resultados. Puedes
          reabrirlo y seguir donde lo dejaste.
        </p>
      )}
    </div>
  );
}

function ArchiveCard({
  archive,
  expanded,
  detail,
  detailError,
  onToggleDetail,
  onRetryDetail,
}: {
  archive: Archive;
  expanded: boolean;
  detail?: ArchiveDetail;
  detailError: Error | null;
  onToggleDetail: () => void;
  onRetryDetail: () => void;
}) {
  const [primaryFile, ...extraFiles] = archive.files ?? [];

  const summaryParts: string[] = [];
  if (archive.row_count != null) {
    summaryParts.push(`${formatNumberEs(archive.row_count)} filas`);
  }
  if (archive.column_count != null) {
    summaryParts.push(`${formatNumberEs(archive.column_count)} columnas`);
  }
  const summary = summaryParts.join(" · ");

  return (
    <div
      style={{
        border: `1px solid ${colors.borderLight}`,
        borderRadius: 8,
        padding: "16px 20px",
        marginBottom: 12,
        background: "#fff",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h2
            style={{
              margin: "0 0 6px",
              fontSize: 15,
              color: colors.textPrimary,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {archive.name}
          </h2>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            {primaryFile && <span style={chipStyle}>{primaryFile}</span>}
            {extraFiles.length > 0 && (
              <span style={mutedChipStyle}>+{extraFiles.length}</span>
            )}
            <span style={{ fontSize: 12, color: colors.textMuted }}>
              {archive.created_at
                ? formatRelativeTimeEs(archive.created_at)
                : "—"}
            </span>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: 8,
            flexShrink: 0,
          }}
        >
          {summary && (
            <div style={{ fontSize: 13, color: colors.textMuted }}>
              {summary}
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <button
              type="button"
              disabled
              title="Disponible próximamente"
              aria-label="Reabrir — Disponible próximamente"
              style={inertActionStyle}
            >
              Reabrir
            </button>
            <button
              type="button"
              disabled
              title="Disponible próximamente"
              aria-label="Exportar — Disponible próximamente"
              style={inertActionStyle}
            >
              Exportar
            </button>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <button type="button" onClick={onToggleDetail} style={detailToggleStyle}>
          {expanded ? "Ocultar detalle" : "Ver detalle"}
        </button>
        {expanded && detailError && (
          <ErrorCard
            title={detailErrorTitle}
            error={detailError}
            onRetry={onRetryDetail}
            actionLabel="Reintentar"
          />
        )}
        {expanded && !detailError && detail?.payload && (
          <pre
            style={{
              marginTop: 12,
              maxHeight: 300,
              overflow: "auto",
              fontSize: "0.85em",
            }}
          >
            {JSON.stringify(detail.payload, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
