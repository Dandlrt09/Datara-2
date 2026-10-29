import { useCallback, useId, useRef, useState, type FormEvent } from "react";
import { useFocusTrap } from "./WizardOverlay/useFocusTrap";
import { useUpdateName } from "../queries/useAuth";
import { ApiError } from "../lib/api";

/**
 * Longest name the server accepts, mirrored here so the input stops the user
 * before the request leaks a 422 (T1/D4).
 */
export const MAX_NAME_LENGTH = 50;

/**
 * Notice the profile screen shows after the name is saved (T1/D7). Exported so
 * the screen that renders it and the tests that assert it share one copy.
 */
export const NAME_UPDATED_NOTICE = "Nombre actualizado.";

/** Map a failed request to the copy the user reads inside the dialog (D7). */
function updateNameErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 422) {
    return `El nombre no puede tener más de ${MAX_NAME_LENGTH} caracteres.`;
  }
  return "No se pudo guardar el nombre. Vuelve a intentarlo.";
}

export interface NameDialogProps {
  /** Whether the dialog is visible. When false, nothing is rendered. */
  open: boolean;
  /** The name stored today, or null when the user never chose one. */
  initialName: string | null;
  /** Called after the request succeeds; the parent closes the dialog. */
  onSuccess: () => void;
  /** Called when the user cancels or presses Escape. */
  onCancel: () => void;
}

/**
 * Accessible modal for editing the display name (T1).
 *
 * Follows the repo's dialog pattern (D4 of `profile-section.md`, same as
 * `ChangePasswordDialog`): `useFocusTrap` for Escape, Tab wrap and focus
 * save/restore; default focus on Cancel so Enter never submits by accident; both
 * actions disabled while the request is in flight. No password gate: the name is
 * display only (D5). Emptying the field is refused with an inline warning (D3
 * rewritten): there is no way back to "no name" from the profile, so the input
 * carries no `required` but a blank submit never reaches the mutation.
 */
export function NameDialog({ open, ...props }: NameDialogProps) {
  if (!open) return null;
  return <NameDialogContent {...props} />;
}

function NameDialogContent({
  initialName,
  onSuccess,
  onCancel,
}: Omit<NameDialogProps, "open">) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const inputId = useId();
  const [name, setName] = useState(initialName ?? "");
  const [error, setError] = useState<string | null>(null);
  const updateName = useUpdateName();
  const pending = updateName.isPending;

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
    // A blank name is refused before the request (D3 rewritten): leaving the
    // field empty no longer clears the name, and the user gets a warning.
    if (name.trim() === "") {
      setError("El nombre no puede quedar vacío.");
      return;
    }
    // The raw value travels as typed: trimming and collapsing are the server's
    // job (D3), so both sides cannot disagree about what was stored.
    updateName.mutate(
      { name },
      {
        onSuccess: () => onSuccess(),
        onError: (err) => setError(updateNameErrorMessage(err)),
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
          Editar nombre
        </h2>
        <form onSubmit={handleSubmit}>
          <label
            htmlFor={inputId}
            style={{ display: "block", marginBottom: 6, color: "#444" }}
          >
            Nombre
          </label>
          <input
            id={inputId}
            type="text"
            value={name}
            maxLength={MAX_NAME_LENGTH}
            onChange={(e) => setName(e.target.value)}
            disabled={pending}
            style={{ width: "100%", padding: 8, boxSizing: "border-box" }}
          />
          <p style={{ margin: "8px 0 0", fontSize: "0.85em", color: "#666" }}>
            {`Hasta ${MAX_NAME_LENGTH} caracteres.`}
          </p>
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
