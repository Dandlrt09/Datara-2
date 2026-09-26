import { useCallback, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useSessions, useCreateSession } from "../queries/useSessions";
import { useFilesGlobal, useUploadFile, useDeleteFile, useProfile, useFileSheets } from "../queries/useFiles";
import { QueryError } from "../components/ErrorCard";
import { SheetPicker } from "../components/SheetPicker";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { UPLOAD_ACCEPT_MAP } from "../lib/uploadFormats";

export default function FilesView() {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  // Set right after a multi-sheet upload so the picker can be shown before
  // the user leaves the page; cleared once a sheet is chosen.
  const [uploadedSheets, setUploadedSheets] = useState<{
    fileId: number;
    sheets: string[];
    sheetName: string | null;
  } | null>(null);

  // File awaiting confirmation before the irreversible delete.
  const [fileToDelete, setFileToDelete] = useState<{ id: number; filename: string } | null>(null);

  const sessions = useSessions();
  const globalFiles = useFilesGlobal();
  const uploadFileMut = useUploadFile();
  const deleteFileMut = useDeleteFile();
  const createSession = useCreateSession();

  // AbortController for the in-flight upload (Cancel button).
  const uploadAbortRef = useRef<AbortController | null>(null);

  // Handle session creation success - select the new session
  const handleCreateSession = useCallback(() => {
    createSession.mutate(undefined, {
      onSuccess: (newSession) => {
        // The session list will refresh via cache invalidation
        // Select the new session by default
        setSelectedSessionId(newSession.id);
      },
    });
  }, [createSession]);

  // Default to most recent session once sessions load
  const sessionList = sessions.data ?? [];
  const effectiveSessionId = selectedSessionId ?? sessionList[0]?.id ?? null;

  const hasSessions = sessionList.length > 0;

  const onDrop = useCallback(
    async (accepted: File[]) => {
      if (!accepted.length || !effectiveSessionId) return;
      if (uploadFileMut.isPending) return; // one upload at a time
      const file = accepted[0];
      if (!file) return;
      const controller = new AbortController();
      uploadAbortRef.current = controller;
      setUploadedSheets(null);
      try {
        const result = await uploadFileMut.mutateAsync({
          sessionId: effectiveSessionId,
          file,
          signal: controller.signal,
        });
        if (result?.sheets && result.sheets.length > 1) {
          setUploadedSheets({
            fileId: result.id,
            sheets: result.sheets,
            sheetName: result.sheet_name ?? null,
          });
        }
      } catch {
        // The upload error banner below renders the failure.
      }
    },
    [effectiveSessionId, uploadFileMut]
  );

  const handleCancelUpload = useCallback(() => {
    uploadAbortRef.current?.abort();
  }, []);

  // The DELETE request only fires after the user confirms in the dialog.
  const handleCancelDelete = useCallback(() => {
    setFileToDelete(null);
  }, []);

  const handleConfirmDelete = useCallback(() => {
    if (!fileToDelete) return;
    deleteFileMut.mutate(fileToDelete.id);
    setFileToDelete(null);
  }, [deleteFileMut, fileToDelete]);

  const uploadError = uploadFileMut.error as Error | null;
  const uploadAborted = uploadFileMut.isError && uploadError?.name === "AbortError";

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: UPLOAD_ACCEPT_MAP,
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
          <div>
            <button
              onClick={handleCreateSession}
              disabled={createSession.isPending}
              style={{
                padding: "12px 24px",
                fontSize: "1em",
                backgroundColor: "#007bff",
                color: "white",
                border: "none",
                borderRadius: "4px",
                cursor: createSession.isPending ? "not-allowed" : "pointer",
                marginBottom: "12px",
              }}
            >
              {createSession.isPending ? "Creating session..." : "Create a chat session"}
            </button>
            {createSession.isError && (
              <p role="alert" style={{ color: "red", marginTop: "8px" }}>
                Failed to create session: {(createSession.error as Error)?.message || "Unknown error"}
              </p>
            )}
            <p style={{ fontSize: "0.9em", color: "#666", marginTop: "8px" }}>
              Create a chat session to upload files
            </p>
          </div>
        ) : isDragActive ? (
          <p>Drop file here...</p>
        ) : (
          <p>Drag and drop a CSV, XLSX, JSON, or TSV file, or click to select</p>
        )}
      </div>

      {/* In-flight upload status with cancel */}
      {uploadFileMut.isPending && (
        <div role="status" style={{ marginBottom: 16 }}>
          <span style={{ marginRight: 8 }}>Uploading file…</span>
          <button onClick={handleCancelUpload}>Cancel</button>
        </div>
      )}

      {/* Upload mutation error */}
      {uploadFileMut.isError && (
        <p
          role="alert"
          style={{ color: uploadAborted ? "#555" : "red", marginBottom: 16 }}
        >
          {uploadAborted
            ? "Upload cancelled"
            : `Upload failed: ${uploadError?.message ?? "Unknown error"}`}
        </p>
      )}

      {/* Multi-sheet workbook: warn and let the user pick a sheet right
          after upload, so the first sheet never silently wins. */}
      {uploadedSheets && (
        <SheetPicker
          fileId={uploadedSheets.fileId}
          sheets={uploadedSheets.sheets}
          currentSheet={uploadedSheets.sheetName}
          onSelected={() => setUploadedSheets(null)}
        />
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
                <FileRow
                  key={f.id}
                  file={f}
                  onDelete={() => setFileToDelete({ id: f.id, filename: f.filename })}
                  deletePending={deleteFileMut.isPending}
                />
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

      <ConfirmDialog
        open={fileToDelete !== null}
        title="Delete file"
        message={
          fileToDelete
            ? `Delete "${fileToDelete.filename}"? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete file"
        cancelLabel="Cancel"
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
      />
    </div>
  );
}

function FileRow({
  file,
  onDelete,
  deletePending,
}: {
  file: { id: number; filename: string; format: string; row_count?: number | null; size_bytes: number; session_title: string | null; has_profile?: boolean };
  onDelete: () => void;
  deletePending: boolean;
}) {
  const { data: profile } = useProfile(file.id);
  const isXlsx = file.format === "xlsx";
  // Lazy per-row sheet list: only fetched when the user opens the picker,
  // so an already-uploaded workbook (possibly pre-F3) can be switched too.
  const [showSheets, setShowSheets] = useState(false);
  const sheetsQuery = useFileSheets(isXlsx ? file.id : null, showSheets);
  const hasMultipleSheets = (sheetsQuery.data?.sheets.length ?? 0) > 1;

  return (
    <tr>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>
        {file.filename}
        {file.has_profile === false && (
          <span
            title="This file has no profile and is not ready for chat"
            style={{
              marginLeft: 8,
              padding: "2px 6px",
              fontSize: "0.75em",
              borderRadius: 4,
              background: "#fff3cd",
              color: "#856404",
              border: "1px solid #ffeeba",
            }}
          >
            Not profiled
          </span>
        )}
      </td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.format}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.row_count ?? "—"}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{(file.size_bytes / 1024).toFixed(1)} KB</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.session_title ?? "—"}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>
        {isXlsx && (
          <button
            onClick={() => setShowSheets((v) => !v)}
            style={{ marginRight: 8 }}
          >
            {showSheets ? "Hide sheets" : "Sheets"}
          </button>
        )}
        {profile && (
          <details>
            <summary>Profile</summary>
            <pre style={{ fontSize: "0.85em", maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(profile, null, 2)}
            </pre>
          </details>
        )}
        {showSheets && sheetsQuery.isLoading && !sheetsQuery.data && (
          <span style={{ marginRight: 8, color: "#777" }}>Reading sheets…</span>
        )}
        {showSheets && sheetsQuery.isError && !sheetsQuery.data && (
          <span style={{ marginRight: 8, color: "red" }}>Could not read sheets</span>
        )}
        {showSheets && sheetsQuery.data && !hasMultipleSheets && (
          <span style={{ marginRight: 8, color: "#777" }}>Only one sheet</span>
        )}
        {showSheets && hasMultipleSheets && sheetsQuery.data && (
          <SheetPicker
            fileId={file.id}
            sheets={sheetsQuery.data.sheets}
            currentSheet={sheetsQuery.data.default_sheet}
          />
        )}
        <button
          onClick={onDelete}
          disabled={deletePending}
          style={{ marginLeft: 8, color: "red", cursor: deletePending ? "not-allowed" : "pointer" }}
        >
          Delete
        </button>
      </td>
    </tr>
  );
}