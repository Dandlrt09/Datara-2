import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMe, useLogout } from "../queries/useAuth";
import {
  ChangePasswordDialog,
  PASSWORD_CHANGED_NOTICE,
} from "../components/ChangePasswordDialog";
import { displayNameFromEmail } from "../lib/displayName";
import { colors, typography } from "../design/tokens";

// The mockup (Pantallas/settings/perfil.txt) is the structural reference; the
// colors stay on the app's current light inline style (S7).
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
} as const;

const rowLabelStyle = {
  color: colors.textPrimary,
  display: "block",
} as const;

const rowSublabelStyle = {
  color: colors.textMuted,
  fontSize: "0.85em",
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
 * The Perfil screen: account data (read-only), password change and the current
 * session's logout.
 *
 * Reached from the sidebar user block (S6). The name is derived from the email
 * (S2); the email itself is read-only (S3); logout lives here rather than in
 * the sidebar (D1).
 */
export default function ProfileView() {
  const navigate = useNavigate();
  const { data: user, isLoading } = useMe();
  const logout = useLogout();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const handleLogout = async () => {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  };

  if (isLoading) {
    return <p style={{ color: colors.textMuted }}>Cargando perfil…</p>;
  }
  if (!user) return null;

  const name = displayNameFromEmail(user.email);
  const initial = name.charAt(0).toUpperCase();

  return (
    <div style={{ maxWidth: 560 }}>
      <h1 style={{ margin: "0 0 16px", color: colors.textPrimary }}>Perfil</h1>

      {notice && (
        <p
          role="status"
          style={{ marginTop: 0, marginBottom: 16, color: colors.textMuted }}
        >
          {notice}
        </p>
      )}

      <section style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            aria-hidden="true"
            style={{
              width: 48,
              height: 48,
              borderRadius: "50%",
              background: "#f0f0f0",
              color: colors.textPrimary,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "1.25em",
              fontWeight: 600,
              flexShrink: 0,
            }}
          >
            {initial}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <h2 style={{ margin: 0, color: colors.textPrimary }}>{name}</h2>
            <span
              style={{
                fontFamily: typography.fontMono,
                fontSize: "0.85em",
                color: colors.textMuted,
              }}
            >
              {user.email}
            </span>
          </div>
        </div>

        <div
          style={{ borderTop: `1px solid ${colors.borderLight}`, margin: "20px 0" }}
        />

        <div style={rowStyle}>
          <div>
            <span style={rowLabelStyle}>Correo electrónico</span>
            <span style={rowSublabelStyle}>Se usa para iniciar sesión.</span>
          </div>
          <span
            style={{
              fontFamily: typography.fontMono,
              fontSize: "0.85em",
              color: colors.textPrimary,
            }}
          >
            {user.email}
          </span>
        </div>

        <div style={{ ...rowStyle, marginTop: 20 }}>
          <div>
            <span style={rowLabelStyle}>Contraseña</span>
            <span style={rowSublabelStyle}>Se usa para proteger tu cuenta.</span>
          </div>
          <button
            type="button"
            onClick={() => setDialogOpen(true)}
            style={secondaryButtonStyle}
          >
            Cambiar
          </button>
        </div>
      </section>

      <section style={{ ...cardStyle, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <div>
          <span style={rowLabelStyle}>Sesión</span>
          <span style={rowSublabelStyle}>Cierra la sesión en este navegador.</span>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          disabled={logout.isPending}
          style={{
            ...secondaryButtonStyle,
            cursor: logout.isPending ? "not-allowed" : "pointer",
          }}
        >
          Cerrar sesión
        </button>
      </section>

      <ChangePasswordDialog
        open={dialogOpen}
        onSuccess={() => {
          setDialogOpen(false);
          setNotice(PASSWORD_CHANGED_NOTICE);
        }}
        onCancel={() => setDialogOpen(false)}
      />
    </div>
  );
}
