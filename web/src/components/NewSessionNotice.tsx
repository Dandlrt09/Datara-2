import {
  useAcknowledgeNewSession,
  useActiveSessions,
} from "../queries/useAuth";
import { formatTimestamp, usePreferences } from "../lib/preferences";
import { colors, typography } from "../design/tokens";

// Informational banner: same light inline style as the profile cards.
const bannerStyle = {
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
  background: colors.surfaceSubtle,
  display: "flex",
  flexDirection: "column",
  gap: 8,
} as const;

const titleStyle = {
  color: colors.textPrimary,
} as const;

const bodyStyle = {
  margin: 0,
  color: colors.textMuted,
  fontSize: typography.fontSize.sm,
} as const;

const buttonStyle = {
  alignSelf: "flex-start",
  padding: "6px 12px",
  fontSize: 13,
  borderRadius: 6,
  border: `1px solid ${colors.borderLight}`,
  background: "#fff",
  color: colors.textPrimary,
  cursor: "pointer",
} as const;

/**
 * In-app notice that another browser opened a session (S4/S6).
 *
 * The server derives the flag from the session list and stores the "already
 * seen" mark per user (D4), so the banner appears once, survives reloads and
 * does not follow the user to another browser. `Entendido` marks it seen.
 */
export default function NewSessionNotice() {
  const { data } = useActiveSessions();
  const acknowledge = useAcknowledgeNewSession();
  const { dateFormat } = usePreferences();

  const newSessionAt = data?.new_session_at ?? null;
  if (!newSessionAt) return null;

  return (
    <section role="status" style={bannerStyle}>
      <strong style={titleStyle}>Entró una nueva sesión</strong>
      <p style={bodyStyle}>
        {`Se abrió una sesión el ${formatTimestamp(
          newSessionAt,
          dateFormat,
        )} desde otro navegador. Si no fuiste vos, cambiá tu contraseña y cerrá las demás.`}
      </p>
      <button
        type="button"
        onClick={() => acknowledge.mutate()}
        disabled={acknowledge.isPending}
        style={{
          ...buttonStyle,
          cursor: acknowledge.isPending ? "not-allowed" : "pointer",
        }}
      >
        Entendido
      </button>
    </section>
  );
}
