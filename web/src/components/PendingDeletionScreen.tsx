import { useNavigate } from "react-router-dom";
import { useCancelAccountDeletion, useLogout } from "../queries/useAuth";
import { formatTimestamp, usePreferences } from "../lib/preferences";
import { colors } from "../design/tokens";

/** Copy for the blocked screen's heading. Exported so the screen and its tests
 * share one string (S7). */
export const PENDING_DELETION_HEADING = "Tu cuenta se eliminará";

export interface PendingDeletionScreenProps {
  /** Scheduled purge deadline, exactly as `GET /api/auth/me` returns it. */
  deadline: string;
}

/**
 * Blocking screen shown while the account is scheduled for deletion (S6/S7).
 *
 * The account cannot be used during the grace period: the only two paths are
 * cancelling the deletion (which returns to the normal app) or signing out
 * (which leaves the schedule untouched, S8). Mounted by `AppShell` *before*
 * the shell's data hooks, so a pending account opens no session/file queries
 * or SSE stream (D6). The deadline is rendered with the user's date-format
 * preference (D7).
 */
export function PendingDeletionScreen({ deadline }: PendingDeletionScreenProps) {
  const navigate = useNavigate();
  const { dateFormat } = usePreferences();
  const cancel = useCancelAccountDeletion();
  const logout = useLogout();
  const busy = cancel.isPending || logout.isPending;

  const handleLogout = async () => {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  };

  return (
    <div
      style={{
        maxWidth: 520,
        margin: "80px auto",
        padding: 24,
        border: "1px solid #f2b8b5",
        borderRadius: 8,
        background: "#fff8f7",
      }}
    >
      <h1 style={{ margin: "0 0 12px", color: "#c62828" }}>
        {PENDING_DELETION_HEADING}
      </h1>
      <p style={{ margin: "0 0 12px", color: colors.textPrimary }}>
        Eliminación programada: {formatTimestamp(deadline, dateFormat)}.
      </p>
      <p style={{ margin: "0 0 24px", color: colors.textMuted }}>
        Mientras esté programado el borrado no puedes usar la app. Puedes
        cancelarlo para volver a usar tu cuenta, o cerrar sesión: el borrado
        seguirá programado.
      </p>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button
          type="button"
          onClick={handleLogout}
          disabled={busy}
          style={{
            padding: "8px 14px",
            borderRadius: 6,
            border: `1px solid ${colors.borderLight}`,
            background: "#fff",
            color: colors.textPrimary,
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          Cerrar sesión
        </button>
        <button
          type="button"
          onClick={() => cancel.mutate()}
          disabled={busy}
          style={{
            padding: "8px 14px",
            borderRadius: 6,
            border: "none",
            background: colors.accent,
            color: colors.onAccent,
            cursor: busy ? "not-allowed" : "pointer",
            opacity: busy ? 0.6 : 1,
          }}
        >
          {cancel.isPending ? "Cancelando…" : "Cancelar el borrado"}
        </button>
      </div>
      {cancel.error && (
        <p role="alert" style={{ color: "#c62828", margin: "12px 0 0" }}>
          No se pudo cancelar el borrado. Vuelve a intentarlo.
        </p>
      )}
    </div>
  );
}
