import { useCallback, useId, useRef, useState } from "react";
import { useFocusTrap } from "./WizardOverlay/useFocusTrap";
import {
  usePrivacyPreview,
  useSessionPrivacy,
  useUpdateSessionPrivacy,
} from "../queries/usePrivacy";
import {
  PRIVACY_LEVEL_DESCRIPTIONS,
  PRIVACY_LEVEL_LABELS,
} from "../lib/privacy";
import type { PrivacyLevel } from "../lib/privacy";
import { FilePrivacySelect, PrivacyLevelSelect } from "./PrivacySelect";

export interface PrivacyPanelProps {
  sessionId: string | null;
  /** Whether the dialog is visible. When false, nothing is rendered. */
  open: boolean;
  onClose: () => void;
}

/**
 * Session privacy dialog: the session default, each file's override and the
 * "Ver qué se envía" viewer.
 *
 * Built on the repo's existing `useFocusTrap` and styled inline like
 * `ConfirmDialog` / `SaveAnalysisDialog`. Closes on Escape or the Cerrar
 * button; the queries only run while the panel is mounted.
 */
export function PrivacyPanel({ sessionId, open, ...props }: PrivacyPanelProps) {
  if (!open || !sessionId) return null;
  return <PrivacyPanelContent sessionId={sessionId} {...props} />;
}

function PrivacyPanelContent({
  sessionId,
  onClose,
}: {
  sessionId: string;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const [showPreview, setShowPreview] = useState(false);

  const privacy = useSessionPrivacy(sessionId);
  const updateSession = useUpdateSessionPrivacy();
  const preview = usePrivacyPreview(sessionId, showPreview);

  // Stable callback so the focus-trap effect does not re-run every render.
  const handleEscape = useCallback(() => onClose(), [onClose]);
  useFocusTrap(dialogRef, closeRef, handleEscape);

  // The API returns the raw string; the closed set keeps it a PrivacyLevel.
  const sessionLevel = (privacy.data?.privacy_level ??
    "full") as PrivacyLevel;
  const files = privacy.data?.files ?? [];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{
          background: "white",
          borderRadius: 8,
          boxShadow: "0 4px 20px rgba(0, 0, 0, 0.15)",
          maxWidth: 560,
          width: "90%",
          maxHeight: "85vh",
          overflowY: "auto",
          padding: 24,
          position: "relative",
        }}
      >
        <h2 id={titleId} style={{ margin: "0 0 12px" }}>
          Privacidad
        </h2>
        <p style={{ color: "#444", marginTop: 0 }}>
          Elige qué se envía al proveedor del modelo. Cada archivo puede heredar
          la configuración de la sesión o usar la suya.
        </p>

        <label style={{ display: "block", marginBottom: 4 }}>
          <span style={{ display: "block", marginBottom: 4 }}>
            Nivel de la sesión
          </span>
          <PrivacyLevelSelect
            label="Nivel de privacidad de la sesión"
            value={sessionLevel}
            disabled={updateSession.isPending || privacy.isLoading}
            onChange={(level) =>
              updateSession.mutate({ sessionId, privacyLevel: level })
            }
          />
        </label>
        <p style={{ color: "#666", margin: "0 0 20px", fontSize: "0.9em" }}>
          {PRIVACY_LEVEL_LABELS[sessionLevel]}:{" "}
          {PRIVACY_LEVEL_DESCRIPTIONS[sessionLevel]}
        </p>

        <h3 style={{ margin: "0 0 8px" }}>Archivos</h3>
        {privacy.isError && (
          <p role="alert" style={{ color: "#c62828", margin: "0 0 8px" }}>
            No se pudo cargar la privacidad de la sesión.
          </p>
        )}
        {!privacy.isError && files.length === 0 && (
          <p style={{ color: "#666" }}>No hay archivos en esta sesión.</p>
        )}
        {files.length > 0 && (
          <ul style={{ listStyle: "none", padding: 0, margin: "0 0 20px" }}>
            {files.map((file) => (
              <li
                key={file.file_id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  padding: "8px 0",
                  borderBottom: "1px solid #eee",
                }}
              >
                <span
                  style={{
                    flex: 1,
                    minWidth: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={file.filename}
                >
                  {file.filename}
                </span>
                <FilePrivacySelect
                  fileId={file.file_id}
                  sessionId={sessionId}
                  filename={file.filename}
                />
              </li>
            ))}
          </ul>
        )}

        <button type="button" onClick={() => setShowPreview((v) => !v)}>
          {showPreview ? "Ocultar qué se envía" : "Ver qué se envía"}
        </button>

        {showPreview && (
          <div style={{ marginTop: 12 }}>
            {preview.isLoading && <p>Cargando…</p>}
            {preview.isError && (
              <p role="alert" style={{ color: "#c62828" }}>
                No se pudo cargar la vista previa.
              </p>
            )}
            {preview.data && (
              <pre
                data-testid="privacy-preview"
                style={{
                  background: "#f5f5f5",
                  padding: 12,
                  borderRadius: 4,
                  overflowX: "auto",
                  maxHeight: 320,
                  fontSize: "0.85em",
                }}
              >
                {JSON.stringify(preview.data, null, 2)}
              </pre>
            )}
          </div>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginTop: 24,
          }}
        >
          <button ref={closeRef} type="button" onClick={onClose}>
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
}
