import {
  useActiveSessions,
  useCloseOtherSessions,
  useCloseSession,
} from "../queries/useAuth";
import { describeUserAgent } from "../lib/userAgent";
import { formatTimestamp, usePreferences } from "../lib/preferences";
import { colors, typography } from "../design/tokens";

// Same current light inline style as the rest of ProfileView (the Dark Cockpit
// repaint is a later work).
const cardStyle = {
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 8,
  padding: 24,
  marginBottom: 16,
} as const;

const rowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 16,
  marginTop: 16,
} as const;

const labelStyle = {
  color: colors.textPrimary,
  display: "block",
} as const;

const sublabelStyle = {
  color: colors.textMuted,
  fontSize: "0.85em",
  display: "block",
} as const;

const badgeStyle = {
  padding: "4px 10px",
  fontSize: 12,
  borderRadius: 999,
  border: `1px solid ${colors.borderLight}`,
  background: "#f0f0f0",
  color: colors.textPrimary,
  flexShrink: 0,
} as const;

const secondaryButtonStyle = {
  padding: "6px 12px",
  fontSize: 13,
  borderRadius: 6,
  border: `1px solid ${colors.borderLight}`,
  background: "#fff",
  color: colors.textPrimary,
  cursor: "pointer",
  flexShrink: 0,
} as const;

/**
 * List of the signed-in user's open sessions (T2.4).
 *
 * Derived from `GET /api/auth/sessions`: each row names the browser and the
 * last real activity, the current row is badged and cannot be closed (D3),
 * and the other rows can be closed one by one or all at once (D7). The list
 * refreshes itself: every close mutation invalidates `["auth", "sessions"]`.
 */
export default function ActiveSessionsCard() {
  const { data, isLoading } = useActiveSessions();
  const close = useCloseSession();
  const closeOthers = useCloseOtherSessions();
  const { dateFormat } = usePreferences();

  const sessions = data?.sessions ?? [];
  const otherSessions = sessions.filter((session) => !session.is_current);
  const hasError = close.isError || closeOthers.isError;

  return (
    <section style={cardStyle} aria-busy={isLoading}>
      <h2 style={{ margin: 0, color: colors.textPrimary }}>Sesiones activas</h2>
      <p style={{ margin: "4px 0 0", ...sublabelStyle }}>
        Navegadores con la sesión abierta. Cerrá los que no reconozcas.
      </p>

      {sessions.map((session) => {
        const label = describeUserAgent(session.user_agent);
        return (
          <div key={session.id} style={rowStyle}>
            <div>
              <span style={labelStyle}>{label}</span>
              <span style={sublabelStyle}>
                Última actividad:{" "}
                {formatTimestamp(session.last_seen_at, dateFormat)}
              </span>
            </div>
            {session.is_current ? (
              <span style={badgeStyle}>Esta sesión</span>
            ) : (
              <button
                type="button"
                aria-label={`Cerrar la sesión en ${label}`}
                onClick={() => close.mutate(session.id)}
                disabled={close.isPending}
                style={{
                  ...secondaryButtonStyle,
                  cursor: close.isPending ? "not-allowed" : "pointer",
                }}
              >
                Cerrar
              </button>
            )}
          </div>
        );
      })}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          gap: 12,
          marginTop: 20,
        }}
      >
        {hasError && (
          <span
            role="status"
            style={{ color: colors.textMuted, fontSize: typography.fontSize.sm }}
          >
            No se pudo cerrar la sesión. Probá de nuevo.
          </span>
        )}
        <button
          type="button"
          onClick={() => closeOthers.mutate()}
          disabled={otherSessions.length === 0 || closeOthers.isPending}
          style={{
            ...secondaryButtonStyle,
            cursor:
              otherSessions.length === 0 || closeOthers.isPending
                ? "not-allowed"
                : "pointer",
          }}
        >
          Cerrar todas las demás
        </button>
      </div>
    </section>
  );
}
