import { useCallback, useId, useRef, useState, type FormEvent } from "react";
import { useFocusTrap } from "./WizardOverlay/useFocusTrap";
import { useChangePassword } from "../queries/useAuth";
import { ApiError } from "../lib/api";

/**
 * Notice the profile screen shows once the password changed (S4). Exported so
 * the screen that renders it and the tests that assert it share one copy.
 */
export const PASSWORD_CHANGED_NOTICE =
  "Contraseña actualizada. Se cerró la sesión en los otros navegadores.";

/** Map a failed request to the copy the user reads inside the dialog (D3). */
function changePasswordErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "La contraseña actual no es correcta.";
    if (error.status === 422) {
      return "La contraseña nueva debe tener al menos 8 caracteres.";
    }
  }
  return "No se pudo cambiar la contraseña. Vuelve a intentarlo.";
}

export interface ChangePasswordDialogProps {
  /** Whether the dialog is visible. When false, nothing is rendered. */
  open: boolean;
  /** Called after the request succeeds; the parent closes the dialog. */
  onSuccess: () => void;
  /** Called when the user cancels or presses Escape. */
  onCancel: () => void;
}

/**
 * Accessible modal for changing the account password.
 *
 * Follows the repo's dialog pattern (D4): `useFocusTrap` for Escape, Tab wrap
 * and focus save/restore; default focus on Cancel so Enter never submits by
 * accident; both actions disabled while the request is in flight. Dark mockup
 * colors are intentionally not copied — the app is still on its light inline
 * style (S7).
 */
export function ChangePasswordDialog({ open, ...props }: ChangePasswordDialogProps) {
  if (!open) return null;
  return <ChangePasswordDialogContent {...props} />;
}

function ChangePasswordDialogContent({
  onSuccess,
  onCancel,
}: Omit<ChangePasswordDialogProps, "open">) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const currentId = useId();
  const newId = useId();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const changePassword = useChangePassword();
  const pending = changePassword.isPending;

  // Escape and Cancel both close without sending, except while pending: the
  // actions are disabled then, so Escape must not close either.
  const handleEscape = useCallback(() => {
    if (!pending) onCancel();
  }, [pending, onCancel]);

  useFocusTrap(dialogRef, cancelRef, handleEscape);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (pending) return;
    setError(null);
    changePassword.mutate(
      { current_password: currentPassword, new_password: newPassword },
      {
        onSuccess: () => onSuccess(),
        onError: (err) => setError(changePasswordErrorMessage(err)),
      },
    );
  };

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
          Cambiar contraseña
        </h2>
        <form onSubmit={handleSubmit}>
          <label
            htmlFor={currentId}
            style={{ display: "block", marginBottom: 6, color: "#444" }}
          >
            Contraseña actual
          </label>
          <input
            id={currentId}
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            disabled={pending}
            style={{ width: "100%", padding: 8, boxSizing: "border-box" }}
          />
          <label
            htmlFor={newId}
            style={{ display: "block", margin: "12px 0 6px", color: "#444" }}
          >
            Contraseña nueva
          </label>
          <input
            id={newId}
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
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
            <button ref={cancelRef} type="button" onClick={onCancel} disabled={pending}>
              Cancelar
            </button>
            <button
              type="submit"
              disabled={pending}
              style={{
                background: "#007bff",
                color: "white",
                border: "none",
                borderRadius: 4,
                padding: "6px 12px",
                cursor: pending ? "not-allowed" : "pointer",
                opacity: pending ? 0.6 : 1,
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
