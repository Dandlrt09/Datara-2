import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import {
  LOCAL_PASSWORD_MIN_LENGTH,
  useLocalProfile,
  useLocalProfileOpen,
  useLocalProfileRescue,
  useLocalProfileStatus,
  useMe,
} from "../queries/useAuth";

/** The display-name limit the server enforces (D5); kept here so the
 * over-limit rejection reads as a sentence and not as a server string. */
const MAX_NAME_LENGTH = 50;

function detailMessage(error: ApiError): string | null {
  const body = error.body as { detail?: unknown } | undefined;
  return typeof body?.detail === "string" ? body.detail : null;
}

/**
 * Turn a local-profile rejection into the line the analyst reads.
 *
 * 422 is either the blank name or the over-limit one, so the server detail
 * tells them apart; 403 means the app booted hosted, where this screen must
 * not exist.
 */
function localProfileErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "Datara no está en modo local. Abre la app en modo local y vuelve a intentarlo.";
    }
    if (error.status === 422) {
      const detail = detailMessage(error);
      if (detail && /at most/i.test(detail)) {
        return `El nombre puede tener hasta ${MAX_NAME_LENGTH} caracteres.`;
      }
      return "Escribe un nombre para tu perfil.";
    }
  }
  return "No se pudo crear tu perfil. Vuelve a intentarlo.";
}

/** Turn a failed unlock into the line the analyst reads (T4/D4). A wrong
 * password and an unset lock are deliberately the same 401 server-side, so the
 * copy cannot be more specific than the server already is. */
function openErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "Datara no está en modo local. Abre la app en modo local y vuelve a intentarlo.";
    }
    if (error.status === 401) return "La contraseña no es correcta.";
    if (error.status === 404) {
      return "Todavía no hay un perfil local en esta instalación.";
    }
  }
  return "No se pudo abrir tu perfil. Vuelve a intentarlo.";
}

/** Turn a failed rescue into the line the analyst reads (T4/D4). The 422 is the
 * new password being shorter than the backend allows. */
function rescueErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "La clave de rescate no es correcta.";
    if (error.status === 422) {
      return `La contraseña nueva debe tener al menos ${LOCAL_PASSWORD_MIN_LENGTH} caracteres.`;
    }
    if (error.status === 404) {
      return "Todavía no hay un perfil local en esta instalación.";
    }
  }
  return "No se pudo usar la clave de rescate. Vuelve a intentarlo.";
}

function Loading() {
  return <div>Loading...</div>;
}

/**
 * First-run identity (F1 / T2c). In local mode there is no login and no lock by
 * default (L10), so a visitor with no session either creates the profile the
 * first time or is let straight in every later time.
 *
 * It is routed outside `HostedOnly` (that wrapper would bounce it to `/login`)
 * and outside `/app` (AppShell's own guard would bounce it too), but still
 * inside the F3b data-folder gate, which keeps running first.
 */
export default function FirstRunScreen() {
  const navigate = useNavigate();
  const me = useMe();
  const status = useLocalProfileStatus();
  const profile = useLocalProfile();
  const open = useLocalProfileOpen();
  const rescue = useLocalProfileRescue();
  const [name, setName] = useState("");
  // The locked branch (T4/D4): the password form, its rescue path, and the new
  // key the rescue reveals once. The key lives only in this state, never in a
  // store, and the screen waits for the analyst to keep it before leaving.
  const [password, setPassword] = useState("");
  const [showRescue, setShowRescue] = useState(false);
  const [rescueKeyInput, setRescueKeyInput] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRescueKey, setNewRescueKey] = useState<string | null>(null);
  // The auto-open must fire once per mount, even if the mutation re-renders
  // the screen or StrictMode double-invokes the effect.
  const autoOpened = useRef(false);

  const goToApp = () => navigate("/app", { replace: true });

  // Already signed in: straight into the app, no form and no auto-open. While a
  // fresh rescue key is on screen this must WAIT: the rescue already opened a
  // session, and navigating would hide the key before the analyst can keep it.
  useEffect(() => {
    if (me.data && newRescueKey === null) goToApp();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me.data, newRescueKey]);

  // An existing profile opens itself (L10): no click and no confirmation. A
  // LOCKED profile never auto-opens (T4/D4): it must ask for the password, so
  // the effect stands down and the locked branch below renders the form.
  useEffect(() => {
    if (me.isLoading || me.data) return;
    if (!status.isSuccess || !status.data?.exists) return;
    if (status.data.locked) return;
    if (autoOpened.current) return;
    autoOpened.current = true;
    profile.mutate({}, { onSuccess: goToApp });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me.isLoading, me.data, status.isSuccess, status.data]);

  // An install that already has email accounts keeps its login (D3): the local
  // profile is only offered on an empty database, so this visitor goes to the
  // email login instead of the creation form. It loses to the auto-open above,
  // which already returned when a local profile exists.
  useEffect(() => {
    if (me.isLoading || me.data) return;
    if (!status.isSuccess || !status.data) return;
    if (status.data.exists || !status.data.hosted_accounts) return;
    navigate("/login", { replace: true });
  }, [me.isLoading, me.data, status.isSuccess, status.data, navigate]);

  // The one-time rescue key (T4/D4) outranks every other state: the rescue
  // already opened a session, but the key must be readable before we leave.
  if (newRescueKey !== null) {
    return (
      <div style={{ maxWidth: 400, margin: "80px auto", padding: 24 }}>
        <h1>Guarda tu clave nueva</h1>
        <p role="alert" style={{ color: "#b26a00" }}>
          Guarda esta clave nueva: no se vuelve a mostrar.
        </p>
        <pre
          style={{
            fontFamily: "monospace",
            background: "#f5f5f5",
            padding: 12,
            borderRadius: 6,
            overflowWrap: "anywhere",
            whiteSpace: "pre-wrap",
          }}
        >
          <code>{newRescueKey}</code>
        </pre>
        <button
          type="button"
          onClick={() => {
            void (async () => {
              setNewRescueKey(null);
              // The rescue answers only the rotated key; the session itself is
              // already open, so re-read who we are before AppShell gates us.
              await me.refetch();
              goToApp();
            })();
          }}
          style={{ width: "100%", padding: 10 }}
        >
          Continuar
        </button>
      </div>
    );
  }

  if (me.isLoading || me.data) return <Loading />;
  // Do not render an empty shell while the profile probe is in flight.
  if (status.isLoading) return <Loading />;

  // Locked profile (T4/D4): ask for the password instead of opening it, and
  // offer the rescue key as the way back in. There is no other path: losing
  // both the password and the key means starting over (stated below).
  if (status.data?.exists && status.data.locked) {
    return (
      <div style={{ maxWidth: 400, margin: "80px auto", padding: 24 }}>
        <h1>Abre tu perfil</h1>
        <p>Este perfil está protegido con una contraseña.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            open.mutate({ password }, { onSuccess: goToApp });
          }}
        >
          <div style={{ marginBottom: 16 }}>
            <label
              htmlFor="local-open-password"
              style={{ display: "block", marginBottom: 4 }}
            >
              Contraseña
            </label>
            <input
              id="local-open-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              style={{ width: "100%", padding: 8 }}
            />
          </div>
          {open.error != null && (
            <p role="alert" style={{ color: "red" }}>
              {openErrorMessage(open.error)}
            </p>
          )}
          <button
            type="submit"
            disabled={open.isPending}
            style={{ width: "100%", padding: 10 }}
          >
            {open.isPending ? "Abriendo..." : "Abrir"}
          </button>
        </form>

        {!showRescue && (
          <button
            type="button"
            onClick={() => setShowRescue(true)}
            style={{ marginTop: 12, background: "none", border: "none", padding: 0, color: "#0066cc", cursor: "pointer" }}
          >
            Usar la clave de rescate
          </button>
        )}

        {showRescue && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              rescue.mutate(
                { rescue_key: rescueKeyInput, new_password: newPassword },
                { onSuccess: (data) => setNewRescueKey(data.rescue_key) },
              );
            }}
            style={{ marginTop: 16, borderTop: "1px solid #e0e0e0", paddingTop: 16 }}
          >
            <div style={{ marginBottom: 12 }}>
              <label
                htmlFor="local-rescue-key"
                style={{ display: "block", marginBottom: 4 }}
              >
                Clave de rescate
              </label>
              <input
                id="local-rescue-key"
                value={rescueKeyInput}
                onChange={(event) => setRescueKeyInput(event.target.value)}
                style={{ width: "100%", padding: 8 }}
              />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label
                htmlFor="local-rescue-password"
                style={{ display: "block", marginBottom: 4 }}
              >
                Contraseña nueva
              </label>
              <input
                id="local-rescue-password"
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                style={{ width: "100%", padding: 8 }}
              />
            </div>
            {rescue.error != null && (
              <p role="alert" style={{ color: "red" }}>
                {rescueErrorMessage(rescue.error)}
              </p>
            )}
            <button
              type="submit"
              disabled={rescue.isPending}
              style={{ width: "100%", padding: 10 }}
            >
              {rescue.isPending ? "Guardando..." : "Usar clave de rescate"}
            </button>
          </form>
        )}

        <p style={{ color: "#888", fontSize: "0.9em", marginTop: 20 }}>
          Si olvidas la contraseña y pierdes la clave de rescate, la única salida
          es empezar de cero.
        </p>
      </div>
    );
  }

  if (status.data?.exists) {
    if (profile.isError) {
      return (
        <div style={{ maxWidth: 400, margin: "80px auto", padding: 24 }}>
          <h1>Crea tu perfil</h1>
          <p role="alert" style={{ color: "red" }}>
            {localProfileErrorMessage(profile.error)}
          </p>
          <button
            type="button"
            onClick={() => profile.mutate({}, { onSuccess: goToApp })}
            disabled={profile.isPending}
            style={{ padding: 10 }}
          >
            Vuelve a intentarlo
          </button>
        </div>
      );
    }
    return (
      <div style={{ maxWidth: 400, margin: "80px auto", padding: 24 }}>
        <h1>Datara</h1>
        <p role="status">Abriendo tu perfil...</p>
      </div>
    );
  }

  // While the redirect to /login is in flight, never flash the name form: this
  // install offers the email login, not a new local profile (D3).
  if (status.data?.hosted_accounts) return <Loading />;

  return (
    <div style={{ maxWidth: 400, margin: "80px auto", padding: 24 }}>
      <h1>Crea tu perfil</h1>
      <p>Así es como Datara te va a llamar en este equipo.</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          profile.mutate({ name }, { onSuccess: goToApp });
        }}
      >
        <div style={{ marginBottom: 16 }}>
          <label
            htmlFor="local-profile-name"
            style={{ display: "block", marginBottom: 4 }}
          >
            Nombre
          </label>
          <input
            id="local-profile-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Tu nombre"
            style={{ width: "100%", padding: 8 }}
          />
        </div>
        {profile.error != null && (
          <p role="alert" style={{ color: "red" }}>
            {localProfileErrorMessage(profile.error)}
          </p>
        )}
        <button
          type="submit"
          disabled={profile.isPending}
          style={{ width: "100%", padding: 10 }}
        >
          {profile.isPending ? "Creando..." : "Crear perfil"}
        </button>
      </form>
    </div>
  );
}
