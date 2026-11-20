import { useState, type FormEvent } from "react";
import {
  LOCAL_PASSWORD_MIN_LENGTH,
  useDeclineLockStep,
  useLocalProfileLock,
} from "../queries/useAuth";
import { colors, typography } from "../design/tokens";

export interface LockStepScreenProps {
  /** Called once the step is answered (the lock is on, or the analyst chose
   * "ahora no"). The gate that renders this screen releases on it, so the app
   * continues even before the status query refetches. */
  onAnswered?: () => void;
}

const cardStyle = {
  maxWidth: 440,
  margin: "80px auto",
  padding: 24,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 8,
} as const;

const inputStyle = {
  width: "100%",
  padding: 8,
  boxSizing: "border-box",
} as const;

const primaryButtonStyle = {
  width: "100%",
  padding: 10,
  cursor: "pointer",
} as const;

const secondaryButtonStyle = {
  padding: "6px 12px",
  borderRadius: 6,
  border: `1px solid ${colors.borderLight}`,
  background: "#fff",
  color: colors.textPrimary,
  cursor: "pointer",
  flexShrink: 0,
} as const;

const linkButtonStyle = {
  marginTop: 12,
  background: "none",
  border: "none",
  padding: 0,
  color: colors.accent,
  cursor: "pointer",
} as const;

/**
 * The optional lock step on the onboarding path (F1 / T3, S3, D1).
 *
 * The block is real but was undiscoverable in Perfil, so this screen puts it on
 * the path: after the local profile is created and before the API-key setup, it
 * explains what the lock protects and offers it. The lock itself stays optional
 * (D4): the analyst who does not want it must say "ahora no" explicitly, and
 * that answer is persisted so the step does not come back.
 *
 * Turning the lock on answers the step by returning the one-time rescue key,
 * exactly like the Perfil section does: the raw key is shown once and kept
 * nowhere in the app. The screen waits for "Continuar" so the key cannot be
 * hidden before the analyst can keep it.
 */
export default function LockStepScreen({ onAnswered }: LockStepScreenProps) {
  const lock = useLocalProfileLock();
  const decline = useDeclineLockStep();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rescueKey, setRescueKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // The key is revealed once: replace the form and keep it on screen until the
  // analyst has copied it. Nothing here persists it.
  if (rescueKey !== null) {
    return (
      <div style={cardStyle}>
        <h1>Guarda tu clave de rescate</h1>
        <p style={{ color: colors.textMuted }}>
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
        <button
          type="button"
          onClick={() => onAnswered?.()}
          style={{ ...primaryButtonStyle, marginTop: 20 }}
        >
          Continuar
        </button>
      </div>
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

  const handleDecline = () => {
    setError(null);
    decline.mutate(undefined, {
      onSuccess: () => onAnswered?.(),
      onError: () =>
        setError("No se pudo guardar tu elección. Vuelve a intentarlo."),
    });
  };

  return (
    <div style={cardStyle}>
      <h1>Protege tu perfil</h1>
      <p style={{ color: colors.textMuted }}>
        Si activas el bloqueo, Datara te va a pedir una contraseña cada vez que
        abras la app en este equipo. Sirve para que nadie más entre a tu perfil
        sin permiso.
      </p>
      <p style={{ color: colors.textMuted }}>
        El bloqueo es opcional. Si no lo quieres ahora, elige «Ahora no».
      </p>
      <form onSubmit={handleSubmit} style={{ marginTop: 16 }}>
        <div style={{ marginBottom: 12 }}>
          <label
            htmlFor="lock-step-password"
            style={{ display: "block", marginBottom: 4 }}
          >
            Contraseña
          </label>
          <input
            id="lock-step-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            style={inputStyle}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label
            htmlFor="lock-step-confirm"
            style={{ display: "block", marginBottom: 4 }}
          >
            Repite la contraseña
          </label>
          <input
            id="lock-step-confirm"
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
        <button type="submit" disabled={lock.isPending} style={primaryButtonStyle}>
          {lock.isPending ? "Activando..." : "Activar el bloqueo"}
        </button>
      </form>
      <button
        type="button"
        onClick={handleDecline}
        disabled={decline.isPending}
        style={linkButtonStyle}
      >
        {decline.isPending ? "Guardando..." : "Ahora no"}
      </button>
    </div>
  );
}
