import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useSessions } from "../queries/useSessions";
import { useFilesGlobal, useUploadFile, useDeleteFile, useProfile } from "../queries/useFiles";
import { QueryError } from "../components/ErrorCard";

export default function FilesView() {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  const sessions = useSessions();
  const globalFiles = useFilesGlobal();
  const uploadFileMut = useUploadFile();
  const deleteFileMut = useDeleteFile();

  // Default to most recent session once sessions load
  const sessionList = sessions.data ?? [];
  const effectiveSessionId = selectedSessionId ?? sessionList[0]?.id ?? null;

  const hasSessions = sessionList.length > 0;

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (!accepted.length || !effectiveSessionId) return;
      const file = accepted[0];
      if (!file) return;
      uploadFileMut.mutate({ sessionId: effectiveSessionId, file });
    },
    [effectiveSessionId, uploadFileMut]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/json": [".json"],
      "text/tab-separated-values": [".tsv", ".tab"],
    },
    maxFiles: 1,
  });

  return (
    <div>
      <h1>Files</h1>

      {/* Session picker */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ marginRight: 8 }}>Upload to session:</label>
        <select
          value={effectiveSessionId ?? ""}
          onChange={(e) => setSelectedSessionId(e.target.value || null)}
          disabled={!hasSessions}
          style={{ padding: "6px 12px", minWidth: 200 }}
        >
          {!hasSessions && <option value="">No sessions available</option>}
          {sessionList.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </select>
      </div>

      {/* Upload zone */}
      <div
        {...getRootProps()}
        style={{
          border: "2px dashed #ccc",
          borderRadius: 8,
          padding: 32,
          textAlign: "center",
          cursor: hasSessions ? "pointer" : "not-allowed",
          background: isDragActive ? "#e3f2fd" : "transparent",
          marginBottom: 24,
          opacity: hasSessions ? 1 : 0.5,
        }}
      >
        <input {...getInputProps()} disabled={!hasSessions} />
        {!hasSessions ? (
          <p>Create a chat session before uploading files</p>
        ) : isDragActive ? (
          <p>Drop file here...</p>
        ) : (
          <p>Drag and drop a CSV, XLSX, JSON, or TSV file, or click to select</p>
        )}
      </div>

      {/* Upload mutation error */}
      {uploadFileMut.isError && (
        <p role="alert" style={{ color: "red", marginBottom: 16 }}>
          Upload failed: {(uploadFileMut.error as Error)?.message ?? "Unknown error"}
        </p>
      )}

      {/* Global file list */}
      <QueryError error={globalFiles.error as Error | null} onRetry={() => globalFiles.refetch()}>
        {globalFiles.isLoading && <p>Loading files...</p>}
        {globalFiles.data && globalFiles.data.length === 0 && (
          <p>No files uploaded yet.</p>
        )}
        {globalFiles.data && globalFiles.data.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Filename</th>
                <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Format</th>
                <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Rows</th>
                <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Size</th>
                <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Session</th>
                <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {globalFiles.data.map((f) => (
                <FileRow key={f.id} file={f} onDelete={() => deleteFileMut.mutate(f.id)} />
              ))}
            </tbody>
          </table>
        )}
      </QueryError>

      {/* Delete mutation error */}
      {deleteFileMut.isError && (
        <p role="alert" style={{ color: "red", marginTop: 16 }}>
          Delete failed: {(deleteFileMut.error as Error)?.message ?? "Unknown error"}
        </p>
      )}
    </div>
  );
}

function FileRow({
  file,
  onDelete,
}: {
  file: { id: number; filename: string; format: string; row_count?: number; size_bytes: number; session_title: string | null };
  onDelete: () => void;
}) {
  const { data: profile } = useProfile(file.id);

  return (
    <tr>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.filename}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.format}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.row_count ?? "—"}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{(file.size_bytes / 1024).toFixed(1)} KB</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.session_title ?? "—"}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>
        {profile && (
          <details>
            <summary>Profile</summary>
            <pre style={{ fontSize: "0.85em", maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(profile, null, 2)}
            </pre>
          </details>
        )}
        <button onClick={onDelete} style={{ marginLeft: 8, color: "red" }}>
          Delete
        </button>
      </td>
    </tr>
  );
}