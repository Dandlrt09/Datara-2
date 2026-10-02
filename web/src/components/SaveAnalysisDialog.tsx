import { useCallback, useId, useRef, useState } from "react";
import { useFocusTrap } from "./WizardOverlay/useFocusTrap";

export interface SaveAnalysisDialogProps {
  /** Whether the dialog is visible. When false, nothing is rendered. */
  open: boolean;
  /** Initial value of the name input; the dialog owns the value afterwards. */
  defaultName: string;
  /** Called with the trimmed name when the user confirms. */
  onConfirm: (name: string) => void;
  /** Called when the user cancels or presses Escape. */
  onCancel: () => void;
  /** Disables both actions while a request is in flight. */
  pending?: boolean;
  /** Error copy shown inside the dialog so the user can retry or adjust. */
  error?: string | null;
}

/**
 * Small accessible dialog that names an análisis before saving it.
 *
 * Built on the repo's `useFocusTrap` (Escape, Tab wrap, focus save/restore)
 * and styled inline like `ConfirmDialog`. Default focus lands on the text
 * input so typing starts immediately. There is no backdrop click-to-close:
 * only Escape or an explicit button closes it.
 */
export function SaveAnalysisDialog({ open, ...props }: SaveAnalysisDialogProps) {
  if (!open) return null;
  return <SaveAnalysisDialogContent {...props} />;
}

function SaveAnalysisDialogContent({
  defaultName,
  onConfirm,
  onCancel,
  pending = false,
  error = null,
}: Omit<SaveAnalysisDialogProps, "open">) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const inputId = useId();
  const [name, setName] = useState(defaultName);

  // Escape and Cancel both invoke onCancel without sending a request, except
  // while pending: D2 disables both actions, so Escape must not close either.
  // Stable callback so the focus-trap effect does not re-run every render.
  const handleEscape = useCallback(() => {
    if (!pending) onCancel();
  }, [pending, onCancel]);

  useFocusTrap(dialogRef, inputRef, handleEscape);

  const trimmed = name.trim();
  // The server trims and rejects an empty name (422); guard here so the
  // button never fires a doomed request.
  const confirmDisabled = pending || trimmed.length === 0;

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
          maxWidth: 420,
          width: "90%",
          padding: 24,
          position: "relative",
        }}
      >
        <h2 id={titleId} style={{ margin: "0 0 16px" }}>
          Guardar análisis
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (confirmDisabled) return;
            onConfirm(trimmed);
          }}
        >
          <label
            htmlFor={inputId}
            style={{ display: "block", marginBottom: 6, color: "#444" }}
          >
            Nombre del análisis
          </label>
          <input
            id={inputId}
            ref={inputRef}
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            disabled={pending}
            style={{ width: "100%", padding: 8, boxSizing: "border-box" }}
          />
          {error && (
            <p
              role="alert"
              style={{ color: "#c62828", margin: "8px 0 0", fontSize: "0.9em" }}
            >
              {error}
            </p>
          )}
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 8,
              marginTop: 24,
            }}
          >
            <button type="button" onClick={onCancel} disabled={pending}>
              Cancelar
            </button>
            <button
              type="submit"
              disabled={confirmDisabled}
              style={{
                background: "#007bff",
                color: "white",
                border: "none",
                borderRadius: 4,
                padding: "6px 12px",
                cursor: confirmDisabled ? "not-allowed" : "pointer",
                opacity: confirmDisabled ? 0.6 : 1,
              }}
            >
              {pending ? "Guardando…" : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
