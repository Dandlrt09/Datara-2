import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router-dom";
import { useResetPassword } from "../queries/useAuth";
import { ApiError } from "../lib/api";

interface ResetForm {
  password: string;
  confirmPassword: string;
}

const cardStyle = { maxWidth: 400, margin: "80px auto", padding: 24 };
const labelStyle = { display: "block", fontSize: 14, marginBottom: 4 };
const inputStyle = { width: "100%", padding: 8, boxSizing: "border-box" as const };
const fieldStyle = { marginBottom: 16 };
const errorStyle = { fontSize: 12, color: "#c62828", margin: "4px 0 0" };

/**
 * Turn the reset error into the line the person reads.
 *
 * 400 is the one-shot link being unknown, expired or already used; 422 is a
 * password the server refuses for length. They need different copy because only
 * the second one can be fixed on this screen.
 */
function resetErrorMessage(error: unknown): string {
  switch ((error as ApiError).status) {
    case 400:
      return "El enlace no es válido o ya venció";
    case 422:
      return "La contraseña debe tener al menos 8 caracteres";
    default:
      return "No pudimos restablecer la contraseña. Vuelve a intentarlo.";
  }
}

/**
 * Set a new password from the emailed reset token (S4/D8).
 *
 * The token lives in the query string the mail points at (D9); the form only
 * asks for the new password and its confirmation, with the same single
 * show/hide toggle the register screen uses.
 */
export default function ResetPasswordScreen() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const reset = useResetPassword();
  const [showPasswords, setShowPasswords] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetForm>();

  const onSubmit = async (data: ResetForm) => {
    try {
      await reset.mutateAsync({ token, new_password: data.password });
    } catch {
      // handled by UI state
    }
  };

  if (reset.isSuccess) {
    return (
      <div style={cardStyle}>
        <h1>Contraseña actualizada</h1>
        <p>Ya puedes iniciar sesión con tu nueva contraseña.</p>
        <p style={{ marginTop: 16 }}>
          <Link to="/login">Ir a iniciar sesión</Link>
        </p>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <h1>Nueva contraseña</h1>
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div style={fieldStyle}>
          <label htmlFor="reset-password" style={labelStyle}>
            Nueva contraseña
          </label>
          <input
            {...register("password", {
              required: "Elige una contraseña",
              minLength: {
                value: 8,
                message: "La contraseña debe tener al menos 8 caracteres",
              },
            })}
            id="reset-password"
            type={showPasswords ? "text" : "password"}
            placeholder="Mínimo 8 caracteres"
            style={inputStyle}
          />
          {errors.password && <p style={errorStyle}>{errors.password.message}</p>}
        </div>

        <div style={fieldStyle}>
          <label htmlFor="reset-confirm" style={labelStyle}>
            Repetir contraseña
          </label>
          <input
            {...register("confirmPassword", {
              required: "Repite la contraseña",
              validate: (value, formValues) =>
                value === formValues.password || "Las contraseñas no coinciden",
            })}
            id="reset-confirm"
            type={showPasswords ? "text" : "password"}
            placeholder="Repite tu contraseña"
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

        {reset.error && (
          <p style={{ ...errorStyle, fontSize: 14 }}>
            {resetErrorMessage(reset.error)}
          </p>
        )}

        <button
          type="submit"
          disabled={reset.isPending}
          style={{ width: "100%", padding: 10 }}
        >
          {reset.isPending ? "Guardando…" : "Guardar contraseña"}
        </button>
      </form>
      <p style={{ marginTop: 16 }}>
        <Link to="/login">Volver a iniciar sesión</Link>
      </p>
    </div>
  );
}
