import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  useArchives,
  useArchiveDetail,
  useDeleteArchive,
  useRenameArchive,
  type Archive,
  type ArchiveDetail,
} from "../queries/useArchives";
import { ErrorCard } from "../components/ErrorCard";
import { ConfirmDialog } from "../components/ConfirmDialog";
import ArchiveSnapshot from "../components/ArchiveSnapshot";
import { colors } from "../design/tokens";
import { formatNumberEs } from "../lib/formatNumbers";
import { formatRelativeTimeEs } from "../lib/relativeTime";
import { api } from "../lib/api";
import {
  archiveToMarkdown,
  archiveMarkdownFilename,
  downloadTextFile,
} from "../lib/archiveMarkdown";

/** Case- and accent-insensitive key for the client-side name search. */
function normalizeForSearch(text: string): string {
  return text
    .toLocaleLowerCase("es")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

/** Extract a human-readable message from an ApiError-shaped failure, mirroring
 * the file-rename precedent. Falls back to a neutral Spanish message. */
function actionErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object") {
    const body = (error as { body?: unknown }).body;
    if (body && typeof body === "object") {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
      if (detail && typeof detail === "object") {
        const message = (detail as { message?: unknown }).message;
        if (typeof message === "string" && message.trim()) return message;
      }
    }
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return fallback;
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

const actionButtonStyle = {
  padding: 0,
  border: "none",
  background: "none",
  color: colors.accent,
  fontSize: 13,
  cursor: "pointer",
} as const;

const dangerActionStyle = {
  ...actionButtonStyle,
  color: colors.danger,
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

const listErrorTitle = "No se pudieron cargar los análisis";
const detailErrorTitle = "No se pudo cargar el detalle";
const exportErrorCopy = "No se pudo exportar el análisis";

export default function ArchiveList() {
  const navigate = useNavigate();
  const {
    data,
    isLoading,
    error,
    refetch,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useArchives();
  const [search, setSearch] = useState("");
  const [newestFirst, setNewestFirst] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [archiveToDelete, setArchiveToDelete] = useState<Archive | null>(null);

  const deleteArchive = useDeleteArchive();

  const archives = useMemo(() => data?.pages.flat() ?? [], [data]);

  // Exactly ONE detail fetch for the whole list. `null` disables the query
  // until a card is expanded, which kills the previous per-row N+1.
  const {
    data: detail,
    error: detailError,
    refetch: refetchDetail,
  } = useArchiveDetail(expandedId);

  const visibleArchives = useMemo(() => {
    const list = archives;
    const query = normalizeForSearch(search.trim());
    const filtered = query
      ? list.filter((a) => normalizeForSearch(a.name).includes(query))
      : list;
    // The endpoint already returns DESC; sorting here keeps the order control
    // honest and deterministic for both directions. Entries without a valid
    // created_at always sort last, regardless of direction.
    const timeOf = (a: Archive): number | null => {
      if (!a.created_at) return null;
      const t = Date.parse(a.created_at);
      return Number.isNaN(t) ? null : t;
    };
    return [...filtered].sort((a, b) => {
      const ta = timeOf(a);
      const tb = timeOf(b);
      if (ta === null && tb === null) return 0;
      if (ta === null) return 1;
      if (tb === null) return -1;
      return newestFirst ? tb - ta : ta - tb;
    });
  }, [archives, search, newestFirst]);

  const hasArchives = archives.length > 0;

  const handleReopen = (archive: Archive) => {
    if (archive.chat_session) {
      navigate(`/app/chat/${archive.chat_session}`);
    } else {
      setExpandedId((current) => (current === archive.id ? null : archive.id));
    }
  };

  const handleConfirmDelete = () => {
    if (!archiveToDelete) return;
    deleteArchive.mutate(archiveToDelete.id, {
      onSettled: () => setArchiveToDelete(null),
    });
  };

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

      {deleteArchive.isError && (
        <p role="alert" style={{ color: colors.dangerText, marginBottom: 12 }}>
          {actionErrorMessage(deleteArchive.error, "No se pudo borrar el análisis")}
        </p>
      )}

      {!error && !isLoading && archives.length === 0 && (
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

      {hasArchives && hasNextPage && search.trim().length > 0 && (
        <p style={{ margin: "0 0 12px", fontSize: 12, color: colors.textMuted }}>
          La búsqueda solo cubre los análisis cargados. Usa «Cargar más» para
          ampliar la lista.
        </p>
      )}

      {hasArchives && hasNextPage && !newestFirst && (
        <p style={{ margin: "0 0 12px", fontSize: 12, color: colors.textMuted }}>
          «Más antiguos» solo ordena los análisis cargados. Usa «Cargar más»
          para ampliar la lista.
        </p>
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
                onReopen={() => handleReopen(a)}
                onRequestDelete={() => setArchiveToDelete(a)}
              />
            );
          })}
        </div>
      )}

      {hasArchives && hasNextPage && (
        <div style={{ marginTop: 12 }}>
          <button
            type="button"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            style={{
              ...detailToggleStyle,
              cursor: isFetchingNextPage ? "not-allowed" : "pointer",
            }}
          >
            {isFetchingNextPage ? "Cargando…" : "Cargar más"}
          </button>
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

      <ConfirmDialog
        open={archiveToDelete !== null}
        title="Borrar análisis"
        message={
          archiveToDelete
            ? `Se borrará «${archiveToDelete.name}». Esta acción no se puede deshacer.`
            : ""
        }
        confirmLabel="Borrar"
        cancelLabel="Cancelar"
        onConfirm={handleConfirmDelete}
        onCancel={() => setArchiveToDelete(null)}
        pending={deleteArchive.isPending}
      />
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
  onReopen,
  onRequestDelete,
}: {
  archive: Archive;
  expanded: boolean;
  detail?: ArchiveDetail;
  detailError: Error | null;
  onToggleDetail: () => void;
  onRetryDetail: () => void;
  onReopen: () => void;
  onRequestDelete: () => void;
}) {
  const [primaryFile, ...extraFiles] = archive.files ?? [];

  const renameArchive = useRenameArchive();
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);

  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState(false);

  const summaryParts: string[] = [];
  if (archive.row_count != null) {
    summaryParts.push(`${formatNumberEs(archive.row_count)} filas`);
  }
  if (archive.column_count != null) {
    summaryParts.push(`${formatNumberEs(archive.column_count)} columnas`);
  }
  const summary = summaryParts.join(" · ");

  const startRename = () => {
    setRenameValue(archive.name);
    setRenameError(null);
    renameArchive.reset();
    setIsRenaming(true);
  };

  const cancelRename = () => {
    setIsRenaming(false);
    setRenameValue("");
    setRenameError(null);
    renameArchive.reset();
  };

  const submitRename = () => {
    const name = renameValue.trim();
    if (!name || renameArchive.isPending) return;
    setRenameError(null);
    renameArchive.mutate(
      { id: archive.id, name },
      {
        onSuccess: () => {
          setIsRenaming(false);
          setRenameValue("");
        },
        onError: (error) =>
          setRenameError(
            actionErrorMessage(error, "No se pudo renombrar el análisis"),
          ),
      },
    );
  };

  const handleExport = async () => {
    if (isExporting) return;
    setIsExporting(true);
    setExportError(false);
    try {
      const detailResponse = await api.get<ArchiveDetail>(
        `/api/archives/${archive.id}`,
      );
      downloadTextFile(
        archiveToMarkdown(archive.name, detailResponse.payload),
        archiveMarkdownFilename(archive.name),
      );
    } catch {
      setExportError(true);
    } finally {
      setIsExporting(false);
    }
  };

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
          {isRenaming ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submitRename();
              }}
              style={{ display: "flex", gap: 4, alignItems: "center" }}
            >
              <input
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") cancelRename();
                }}
                autoFocus
                maxLength={200}
                aria-label="Nuevo nombre del análisis"
                style={{ flex: 1, minWidth: 0, padding: "2px 6px", fontSize: "inherit" }}
              />
              <button
                type="submit"
                disabled={!renameValue.trim() || renameArchive.isPending}
              >
                Guardar
              </button>
              <button type="button" onClick={cancelRename}>
                Cancelar
              </button>
            </form>
          ) : (
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
          )}
          {renameError && (
            <p role="alert" style={{ color: colors.dangerText, margin: "4px 0" }}>
              {renameError}
            </p>
          )}
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
            <button type="button" onClick={onReopen} style={actionButtonStyle}>
              Reabrir
            </button>
            <button
              type="button"
              onClick={handleExport}
              disabled={isExporting}
              style={{
                ...actionButtonStyle,
                cursor: isExporting ? "not-allowed" : "pointer",
              }}
            >
              {isExporting ? "Exportando…" : "Exportar"}
            </button>
            <button type="button" onClick={startRename} style={actionButtonStyle}>
              Renombrar
            </button>
            <button
              type="button"
              onClick={onRequestDelete}
              style={dangerActionStyle}
            >
              Borrar
            </button>
          </div>
          {exportError && (
            <p role="alert" style={{ margin: 0, color: colors.dangerText, fontSize: 12 }}>
              {exportErrorCopy}
            </p>
          )}
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
        {expanded && !detailError && detail && (
          <ArchiveSnapshot name={archive.name} payload={detail.payload} />
        )}
      </div>
    </div>
  );
}
