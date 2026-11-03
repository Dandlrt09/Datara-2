import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { useForgotPassword } from "../queries/useAuth";

interface ForgotForm {
  email: string;
}

const cardStyle = { maxWidth: 400, margin: "80px auto", padding: 24 };
const labelStyle = { display: "block", fontSize: 14, marginBottom: 4 };
const inputStyle = { width: "100%", padding: 8, boxSizing: "border-box" as const };
const fieldStyle = { marginBottom: 16 };
const errorStyle = { fontSize: 12, color: "#c62828", margin: "4px 0 0" };

/**
 * Start password recovery (S4/D6).
 *
 * The result never changes what the person reads: whether the address exists or
 * not, the screen shows the same confirmation, so the UI cannot be used to
 * enumerate accounts. Because of that the request settles silently and the
 * message is unconditional.
 */
export default function ForgotPasswordScreen() {
  const forgot = useForgotPassword();
  const [sent, setSent] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotForm>();

  const onSubmit = async (data: ForgotForm) => {
    try {
      await forgot.mutateAsync({ email: data.email });
    } catch {
      // Deliberately swallowed: the visible result must not depend on whether
      // the address has an account (D6).
    }
    setSent(true);
  };

  return (
    <div style={cardStyle}>
      <h1>Recuperar contraseña</h1>
      <p>Escribe tu email y te enviaremos un enlace para restablecerla.</p>
      <form onSubmit={handleSubmit(onSubmit)}>
        <div style={fieldStyle}>
          <label htmlFor="forgot-email" style={labelStyle}>
            Email
          </label>
          <input
            {...register("email", { required: "Ingresa tu email" })}
            id="forgot-email"
            type="email"
            placeholder="tu@correo.com"
            style={inputStyle}
          />
          {errors.email && <p style={errorStyle}>{errors.email.message}</p>}
        </div>
        <button
          type="submit"
          disabled={forgot.isPending}
          style={{ width: "100%", padding: 10 }}
        >
          {forgot.isPending ? "Enviando…" : "Enviar enlace"}
        </button>
      </form>
      {sent && (
        <p role="status" style={{ marginTop: 12 }}>
          Si esa dirección tiene una cuenta, te enviamos un enlace para restablecerla
        </p>
      )}
      <p style={{ marginTop: 16 }}>
        <Link to="/login">Volver a iniciar sesión</Link>
      </p>
    </div>
  );
}
