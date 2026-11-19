import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import {
  useLocalProfile,
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
  const [name, setName] = useState("");
  // The auto-open must fire once per mount, even if the mutation re-renders
  // the screen or StrictMode double-invokes the effect.
  const autoOpened = useRef(false);

  const goToApp = () => navigate("/app", { replace: true });

  // Already signed in: straight into the app, no form and no auto-open.
  useEffect(() => {
    if (me.data) goToApp();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me.data]);

  // An existing profile opens itself (L10): no click and no confirmation.
  useEffect(() => {
    if (me.isLoading || me.data) return;
    if (!status.isSuccess || !status.data?.exists) return;
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

  if (me.isLoading || me.data) return <Loading />;
  // Do not render an empty shell while the profile probe is in flight.
  if (status.isLoading) return <Loading />;

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
