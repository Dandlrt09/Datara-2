import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { useRegister } from "../queries/useAuth";
import { ApiError } from "../lib/api";

interface RegisterForm {
  name: string;
  email: string;
  password: string;
  confirmPassword: string;
}

type Strength = "weak" | "medium" | "strong";

const STRENGTH_LABEL: Record<Strength, string> = {
  weak: "Débil",
  medium: "Media",
  strong: "Fuerte",
};

const STRENGTH_COLOR: Record<Strength, string> = {
  weak: "#c62828",
  medium: "#b26a00",
  strong: "#2e7d32",
};

const STRENGTH_WIDTH: Record<Strength, string> = {
  weak: "33%",
  medium: "66%",
  strong: "100%",
};

/**
 * Rate a password for advice only (S4/D6).
 *
 * The rule the server enforces is the 8-character minimum; this meter never
 * blocks and never promises more than that. It weighs length and how many of
 * the four character classes are present, so the bar moves for a reason the
 * person can act on: "fuerte" needs 12+ characters and 3 classes, "media" needs
 * 8+ and 2 classes.
 */
export function passwordStrength(password: string): Strength | null {
  if (!password) return null;
  const classes = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((rule) =>
    rule.test(password),
  ).length;
  if (password.length >= 12 && classes >= 3) return "strong";
  if (password.length >= 8 && classes >= 2) return "medium";
  return "weak";
}

// The email shape the server accepts (S5 of the security phase): checked here
// only to save a round trip, never as the authority.
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * Turn the register error into the line the person reads.
 *
 * 409 and 422 are states the server actually distinguishes, and 429 is the
 * attempt brake (S3 of the security phase): without a case here the user would
 * read a generic failure while the account is fine and they merely have to
 * wait.
 */
function registerErrorMessage(error: unknown): string {
  switch ((error as ApiError).status) {
    case 409:
      return "Ese email ya tiene una cuenta";
    case 422:
      return "Revisá los datos ingresados";
    case 429:
      return "Demasiados intentos, probá más tarde";
    default:
      return "No pudimos crear la cuenta. Vuelve a intentarlo.";
  }
}

const labelStyle = { display: "block", fontSize: 14, marginBottom: 4 };
const inputStyle = { width: "100%", padding: 8, boxSizing: "border-box" as const };
const hintStyle = { fontSize: 12, color: "#5f6368", margin: "4px 0 0" };
const errorStyle = { fontSize: 12, color: "#c62828", margin: "4px 0 0" };
const fieldStyle = { marginBottom: 16 };

export default function RegisterScreen() {
  const navigate = useNavigate();
  const registerMut = useRegister();
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<RegisterForm>();

  // One toggle for both password fields: they hold the same secret, so a second
  // control would only ask the same question twice (D3).
  const [showPasswords, setShowPasswords] = useState(false);
  const strength = passwordStrength(watch("password") ?? "");

  const onSubmit = async (data: RegisterForm) => {
    const name = data.name.trim();
    try {
      await registerMut.mutateAsync({
        email: data.email,
        password: data.password,
        // An empty name is not sent at all: the server reads a missing name as
        // "use the email-derived one" (S2), so there is nothing to spell twice.
        ...(name ? { name } : {}),
      });
      // /app decides where to land (guided setup when nothing is configured,
      // chat otherwise): one decision point, not one per entry screen.
      navigate("/app");
    } catch (err) {
      // handled by UI state
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "80px auto", padding: 24 }}>
      <h1>Datara</h1>
      <h2>Crear cuenta</h2>
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div style={fieldStyle}>
          <label htmlFor="register-name" style={labelStyle}>
            Nombre (opcional)
          </label>
          <input
            {...register("name", {
              validate: (value) =>
                value.trim().length <= 50 || "Usá 50 caracteres como máximo",
            })}
            id="register-name"
            type="text"
            placeholder="Daniel"
            aria-describedby="register-name-hint"
            style={inputStyle}
          />
          <p id="register-name-hint" style={hintStyle}>
            Si lo dejás vacío, usamos la parte local de tu email.
          </p>
          {errors.name && <p style={errorStyle}>{errors.name.message}</p>}
        </div>

        <div style={fieldStyle}>
          <label htmlFor="register-email" style={labelStyle}>
            Email
          </label>
          <input
            {...register("email", {
              required: "Ingresá tu email",
              pattern: {
                value: EMAIL_PATTERN,
                message: "Ese email no parece válido",
              },
            })}
            id="register-email"
            type="email"
            placeholder="tu@correo.com"
            style={inputStyle}
          />
          {errors.email && <p style={errorStyle}>{errors.email.message}</p>}
        </div>

        <div style={fieldStyle}>
          <label htmlFor="register-password" style={labelStyle}>
            Contraseña
          </label>
          <input
            {...register("password", {
              required: "Elegí una contraseña",
              minLength: {
                value: 8,
                message: "La contraseña debe tener al menos 8 caracteres",
              },
            })}
            id="register-password"
            type={showPasswords ? "text" : "password"}
            placeholder="Mínimo 8 caracteres"
            style={inputStyle}
          />
          {errors.password && <p style={errorStyle}>{errors.password.message}</p>}
          {strength && (
            <div aria-live="polite" style={{ marginTop: 6 }}>
              <div
                style={{
                  height: 4,
                  borderRadius: 2,
                  background: "#e0e0e0",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: STRENGTH_WIDTH[strength],
                    background: STRENGTH_COLOR[strength],
                  }}
                />
              </div>
              <p style={{ ...hintStyle, color: STRENGTH_COLOR[strength] }}>
                Seguridad de la contraseña: <strong>{STRENGTH_LABEL[strength]}</strong>
              </p>
            </div>
          )}
        </div>

        <div style={fieldStyle}>
          <label htmlFor="register-confirm" style={labelStyle}>
            Repetir contraseña
          </label>
          <input
            {...register("confirmPassword", {
              required: "Repetí la contraseña",
              validate: (value, formValues) =>
                value === formValues.password || "Las contraseñas no coinciden",
            })}
            id="register-confirm"
            type={showPasswords ? "text" : "password"}
            placeholder="Repetí tu contraseña"
            style={inputStyle}
          />
          {errors.confirmPassword && (
            <p style={errorStyle}>{errors.confirmPassword.message}</p>
          )}
          <button
            type="button"
            onClick={() => setShowPasswords((visible) => !visible)}
            aria-pressed={showPasswords}
            style={{
              marginTop: 8,
              padding: 0,
              border: "none",
              background: "none",
              color: "#1a73e8",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            {showPasswords ? "Ocultar contraseñas" : "Mostrar contraseñas"}
          </button>
        </div>

        {registerMut.error && (
          <p style={{ ...errorStyle, fontSize: 14 }}>
            {registerErrorMessage(registerMut.error)}
          </p>
        )}

        <button
          type="submit"
          disabled={registerMut.isPending}
          style={{ width: "100%", padding: 10 }}
        >
          {registerMut.isPending ? "Creando cuenta…" : "Crear cuenta"}
        </button>
      </form>
      <p style={{ marginTop: 16 }}>
        ¿Ya tenés cuenta? <Link to="/login">Iniciá sesión</Link>
      </p>
    </div>
  );
}
