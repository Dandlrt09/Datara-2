import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useParams } from "react-router-dom";
import { useFiles, useUploadFile, useDeleteFile, useProfile } from "../queries/useFiles";

export default function FilesView() {
  // Use the first session's files, or allow viewing all files
  const { sessionId } = useParams();
  const { data: files, isLoading } = useFiles(sessionId ?? "__all__");
  const uploadFileMut = useUploadFile();
  const deleteFileMut = useDeleteFile();

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (!accepted.length) return;
      const file = accepted[0];
      if (!file) return;
      uploadFileMut.mutate({ sessionId: sessionId ?? "__all__", file });
    },
    [sessionId, uploadFileMut]
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

      {/* Upload zone */}
      <div
        {...getRootProps()}
        style={{
          border: "2px dashed #ccc",
          borderRadius: 8,
          padding: 32,
          textAlign: "center",
          cursor: "pointer",
          background: isDragActive ? "#e3f2fd" : "transparent",
          marginBottom: 24,
        }}
      >
        <input {...getInputProps()} />
        {isDragActive ? (
          <p>Drop file here...</p>
        ) : (
          <p>Drag and drop a CSV, XLSX, JSON, or TSV file, or click to select</p>
        )}
      </div>

      {/* File list */}
      {isLoading && <p>Loading files...</p>}
      {files && files.length === 0 && <p>No files uploaded yet.</p>}
      {files && files.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Filename</th>
              <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Format</th>
              <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Rows</th>
              <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Size</th>
              <th style={{ borderBottom: "2px solid #ccc", padding: 8, textAlign: "left" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <FileRow key={f.id} file={f} onDelete={() => deleteFileMut.mutate(f.id)} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function FileRow({
  file,
  onDelete,
}: {
  file: { id: number; filename: string; format: string; row_count?: number; size_bytes: number };
  onDelete: () => void;
}) {
  const { data: profile } = useProfile(file.id);

  return (
    <tr>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.filename}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.format}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{file.row_count ?? "—"}</td>
      <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{(file.size_bytes / 1024).toFixed(1)} KB</td>
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