import { useCallback, useId, useRef, useState, type FormEvent } from "react";
import { useFocusTrap } from "./WizardOverlay/useFocusTrap";
import { useRequestAccountDeletion } from "../queries/useAuth";
import { ApiError } from "../lib/api";

/** Word the user has to type to confirm (S2). Exported so the dialog and its
 * tests share one copy. */
export const DELETE_CONFIRMATION_WORD = "ELIMINAR";

/** Notice the login screen shows after a deletion request (S5). Exported so the
 * screen that renders it and the tests that assert it share one copy. */
export const DELETION_SCHEDULED_NOTICE =
  "Tu cuenta se eliminará en 7 días. Inicia sesión para cancelar el borrado.";

/** Map a failed request to the copy the user reads inside the dialog (S2/S9). */
function deleteAccountErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "La contraseña no es correcta.";
    if (error.status === 422) {
      return `Escribí ${DELETE_CONFIRMATION_WORD} para confirmar.`;
    }
  }
  return "No se pudo programar el borrado. Vuelve a intentarlo.";
}

export interface DeleteAccountDialogProps {
  /** Whether the dialog is visible. When false, nothing is rendered. */
  open: boolean;
  /** Called after the request succeeds; the parent closes and redirects. */
  onSuccess: () => void;
  /** Called when the user cancels or presses Escape. */
  onCancel: () => void;
}

/**
 * Accessible modal that schedules the account deletion after the grace period.
 *
 * Two independent gates (S2): the confirmation word and the current password.
 * The server checks the password first, so a wrong password is always a 401
 * regardless of the word (S9). Default focus lands on Cancel so Enter never
 * submits by accident, and both actions lock while the request is in flight.
 */
export function DeleteAccountDialog({ open, ...props }: DeleteAccountDialogProps) {
  if (!open) return null;
  return <DeleteAccountDialogContent {...props} />;
}

function DeleteAccountDialogContent({
  onSuccess,
  onCancel,
}: Omit<DeleteAccountDialogProps, "open">) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const confirmId = useId();
  const passwordId = useId();
  const [confirmation, setConfirmation] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const requestDeletion = useRequestAccountDeletion();
  const pending = requestDeletion.isPending;

  const handleEscape = useCallback(() => {
    if (!pending) onCancel();
  }, [pending, onCancel]);

  useFocusTrap(dialogRef, cancelRef, handleEscape);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (pending) return;
    setError(null);
    requestDeletion.mutate(
      { confirmation, current_password: password },
      {
        onSuccess: () => onSuccess(),
        onError: (err) => setError(deleteAccountErrorMessage(err)),
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
          maxWidth: 460,
          width: "90%",
          padding: 24,
          position: "relative",
        }}
      >
        <h2 id={titleId} style={{ margin: "0 0 12px" }}>
          Eliminar cuenta
        </h2>
        <p style={{ margin: "0 0 8px", color: "#444" }}>
          Tu cuenta se eliminará en 7 días. Antes de esa fecha puedes cancelar el
          borrado iniciando sesión.
        </p>
        <p style={{ margin: "0 0 16px", color: "#c62828", fontSize: "0.9em" }}>
          Se borrarán tus conversaciones, archivos y la configuración del modelo,
          incluida la API key guardada.
        </p>
        <form onSubmit={handleSubmit}>
          <label
            htmlFor={confirmId}
            style={{ display: "block", marginBottom: 6, color: "#444" }}
          >
            Escribí {DELETE_CONFIRMATION_WORD} para confirmar
          </label>
          <input
            id={confirmId}
            type="text"
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            disabled={pending}
            style={{ width: "100%", padding: 8, boxSizing: "border-box" }}
          />
          <label
            htmlFor={passwordId}
            style={{ display: "block", margin: "12px 0 6px", color: "#444" }}
          >
            Contraseña actual
          </label>
          <input
            id={passwordId}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
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
                background: "#c62828",
                color: "white",
                border: "none",
                borderRadius: 4,
                padding: "6px 12px",
                cursor: pending ? "not-allowed" : "pointer",
                opacity: pending ? 0.6 : 1,
              }}
            >
              {pending ? "Eliminando…" : "Eliminar mi cuenta"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
