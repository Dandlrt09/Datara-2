import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  LOCAL_PASSWORD_MIN_LENGTH,
  useLocalProfileLock,
  useLocalProfileStatus,
  useMe,
  useLogout,
} from "../queries/useAuth";
import { useAppConfig } from "../queries/useAppConfig";
import {
  ChangePasswordDialog,
  PASSWORD_CHANGED_NOTICE,
} from "../components/ChangePasswordDialog";
import PreferencesCard from "../components/PreferencesCard";
import ActiveSessionsCard from "../components/ActiveSessionsCard";
import ActivityLogCard from "../components/ActivityLogCard";
import UsageCard from "../components/UsageCard";
import ExportAccountCard from "../components/ExportAccountCard";
import NewSessionNotice from "../components/NewSessionNotice";
import {
  DeleteAccountDialog,
  DELETION_SCHEDULED_NOTICE,
} from "../components/DeleteAccountDialog";
import { NameDialog, NAME_UPDATED_NOTICE } from "../components/NameDialog";
import { resolveDisplayName } from "../lib/displayName";
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

const sectionTitleStyle = {
  margin: "0 0 8px",
  color: colors.textPrimary,
  fontSize: "1.1em",
} as const;

const inputStyle = {
  width: "100%",
  padding: 8,
  boxSizing: "border-box",
} as const;

/**
 * The optional local lock (F1 / T4, D4), rendered only in local mode.
 *
 * There is deliberately NO "turn the lock off" path: D4 grants the one-time
 * rescue key as the way back, not a removal, and inventing one is out of scope.
 * A locked profile changes its password from the Contraseña row above, which
 * writes the same column the lock reads.
 *
 * The rescue key lives only in this component's state, never in a store: the
 * backend keeps only its hash, so this is the single chance to copy it.
 */
function LocalLockSection() {
  const status = useLocalProfileStatus();
  const lock = useLocalProfileLock();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rescueKey, setRescueKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // The key is revealed once: replace the form and keep it on screen until the
  // analyst has copied it (nothing here persists it).
  if (rescueKey !== null) {
    return (
      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Guarda tu clave de rescate</h2>
        <p style={{ ...rowSublabelStyle, marginTop: 0 }}>
          Esta clave se muestra una sola vez. Si olvidas la contraseña, es la
          única forma de volver a entrar.
        </p>
        <pre
          style={{
            fontFamily: typography.fontMono,
            background: "#f5f5f5",
            padding: 12,
            borderRadius: 6,
            overflowWrap: "anywhere",
            whiteSpace: "pre-wrap",
          }}
        >
          <code>{rescueKey}</code>
        </pre>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
          <button
            type="button"
            onClick={() => {
              if (navigator.clipboard) {
                void navigator.clipboard.writeText(rescueKey);
              }
              setCopied(true);
            }}
            style={secondaryButtonStyle}
          >
            {copied ? "Copiada" : "Copiar"}
          </button>
          <span role="alert" style={{ color: "#b26a00", fontSize: "0.9em" }}>
            Guárdala en un lugar seguro. No se vuelve a mostrar.
          </span>
        </div>
      </section>
    );
  }

  if (status.isLoading) return null;

  if (status.data?.locked) {
    return (
      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Bloqueo del perfil</h2>
        <p style={{ margin: 0 }}>Tu perfil está bloqueado con una contraseña.</p>
        <p style={{ ...rowSublabelStyle, marginBottom: 0 }}>
          Para cambiar la contraseña, usa la sección Contraseña de arriba.
        </p>
      </section>
    );
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (password.length < LOCAL_PASSWORD_MIN_LENGTH) {
      setError(
        `La contraseña debe tener al menos ${LOCAL_PASSWORD_MIN_LENGTH} caracteres.`,
      );
      return;
    }
    if (password !== confirm) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    lock.mutate(
      { password },
      {
        onSuccess: (data) => setRescueKey(data.rescue_key),
        onError: () =>
          setError("No se pudo activar el bloqueo. Vuelve a intentarlo."),
      },
    );
  };

  return (
    <section style={cardStyle}>
      <h2 style={sectionTitleStyle}>Bloqueo del perfil</h2>
      <p style={{ ...rowSublabelStyle, marginTop: 0 }}>
        Protege tu perfil con una contraseña. Cada vez que abras Datara en este
        equipo, te la vamos a pedir.
      </p>
      <form onSubmit={handleSubmit} style={{ marginTop: 16 }}>
        <div style={{ marginBottom: 12 }}>
          <label
            htmlFor="local-lock-password"
            style={{ display: "block", marginBottom: 4 }}
          >
            Contraseña
          </label>
          <input
            id="local-lock-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            style={inputStyle}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label
            htmlFor="local-lock-confirm"
            style={{ display: "block", marginBottom: 4 }}
          >
            Repite la contraseña
          </label>
          <input
            id="local-lock-confirm"
            type="password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            style={inputStyle}
          />
        </div>
        {error && (
          <p role="alert" style={{ color: "#c62828", margin: "0 0 12px" }}>
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={lock.isPending}
          style={{ ...secondaryButtonStyle, padding: "8px 14px" }}
        >
          {lock.isPending ? "Activando..." : "Activar bloqueo"}
        </button>
      </form>
    </section>
  );
}

/**
 * The Perfil screen: account data (read-only), password change and the current
 * session's logout.
 *
 * Reached from the sidebar user block (S6). The name is editable here (T1) and
 * the email itself is read-only (S3); logout lives here rather than in the
 * sidebar (D1).
 */
export default function ProfileView() {
  const navigate = useNavigate();
  const { data: user, isLoading } = useMe();
  const config = useAppConfig();
  const logout = useLogout();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [nameDialogOpen, setNameDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const handleLogout = async () => {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  };

  const handleDeletionScheduled = () => {
    // Requesting deletion closes every session server-side (S5): land on the
    // login screen with the notice, where the user can sign in again to cancel.
    setDeleteDialogOpen(false);
    navigate("/login", {
      replace: true,
      state: { notice: DELETION_SCHEDULED_NOTICE },
    });
  };

  if (isLoading) {
    return <p style={{ color: colors.textMuted }}>Cargando perfil…</p>;
  }
  if (!user) return null;

  // One resolver feeds Perfil and the sidebar, so they cannot disagree (T1/D6).
  const name = resolveDisplayName(user.name, user.email);
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


      <NewSessionNotice />

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
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 2,
              minWidth: 0,
            }}
          >
            <h2
              style={{ margin: 0, color: colors.textPrimary, overflowWrap: "anywhere" }}
            >
              {name}
            </h2>
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
            <span style={rowLabelStyle}>Nombre</span>
            <span style={rowSublabelStyle}>
              Así te mostramos en la app.
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ color: colors.textPrimary, overflowWrap: "anywhere" }}>
              {name}
            </span>
            <button
              type="button"
              onClick={() => setNameDialogOpen(true)}
              style={secondaryButtonStyle}
            >
              Editar
            </button>
          </div>
        </div>

        <div style={{ ...rowStyle, marginTop: 20 }}>
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

      {/* The local lock exists only where there is no email (F1 / T4, D4). */}
      {config.data?.mode === "local" && <LocalLockSection />}

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

      <ActiveSessionsCard />
      <ActivityLogCard />
      <UsageCard />

      <ExportAccountCard />

      <PreferencesCard />

      <section
        style={{ ...cardStyle, borderColor: "#f2b8b5", background: "#fff8f7" }}
      >
        <div style={rowStyle}>
          <div>
            <span style={{ ...rowLabelStyle, color: "#c62828" }}>
              Eliminar cuenta
            </span>
            <span style={rowSublabelStyle}>
              Se borra en 7 días. Puedes cancelarlo antes de esa fecha.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setDeleteDialogOpen(true)}
            style={{ ...secondaryButtonStyle, color: "#c62828", borderColor: "#f2b8b5" }}
          >
            Eliminar mi cuenta
          </button>
        </div>
      </section>

      <NameDialog
        open={nameDialogOpen}
        initialName={user.name}
        onSuccess={() => {
          setNameDialogOpen(false);
          setNotice(NAME_UPDATED_NOTICE);
        }}
        onCancel={() => setNameDialogOpen(false)}
      />

      <DeleteAccountDialog
        open={deleteDialogOpen}
        onSuccess={handleDeletionScheduled}
        onCancel={() => setDeleteDialogOpen(false)}
      />

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
