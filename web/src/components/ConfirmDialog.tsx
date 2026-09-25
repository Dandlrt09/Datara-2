import { useId, useRef } from "react";
import { useFocusTrap } from "./WizardOverlay/useFocusTrap";

export interface ConfirmDialogProps {
  /** Whether the dialog is visible. When false, nothing is rendered. */
  open: boolean;
  /** Dialog heading; also the accessible name. */
  title: string;
  /** Body copy naming the target and the consequence. */
  message: string;
  /** Label for the destructive confirm button. */
  confirmLabel?: string;
  /** Label for the safe cancel button. */
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** Disables both actions while a request is in flight. */
  pending?: boolean;
}

/**
 * Small accessible confirmation modal.
 *
 * Built on the repo's existing `useFocusTrap` (Escape, Tab wrap, focus
 * save/restore) and styled inline like `WizardOverlay`. Default focus lands
 * on Cancel so pressing Enter never confirms a destructive action. There is no
 * backdrop click-to-close: only Escape or an explicit button closes it.
 */
export function ConfirmDialog({ open, ...props }: ConfirmDialogProps) {
  if (!open) return null;
  return <ConfirmDialogContent {...props} />;
}

function ConfirmDialogContent({
  title,
  message,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  pending = false,
}: Omit<ConfirmDialogProps, "open">) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  // Escape and Cancel both invoke onCancel without sending a request.
  useFocusTrap(dialogRef, cancelRef, onCancel);

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
        <h2 id={titleId} style={{ margin: "0 0 8px" }}>
          {title}
        </h2>
        <p style={{ margin: "0 0 24px", color: "#444" }}>{message}</p>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button ref={cancelRef} onClick={onCancel} disabled={pending}>
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={pending}
            style={{
              background: "#dc3545",
              color: "white",
              border: "none",
              borderRadius: 4,
              padding: "6px 12px",
              cursor: pending ? "not-allowed" : "pointer",
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
