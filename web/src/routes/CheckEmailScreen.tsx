import { Link, useSearchParams } from "react-router-dom";
import { useResendVerification } from "../queries/useAuth";

const cardStyle = { maxWidth: 400, margin: "80px auto", padding: 24 };

/**
 * The landing after signup (S3/D4).
 *
 * Register no longer opens a session, so this screen tells the person the
 * verification link is on its way and gives them the only useful action while
 * they wait: send it again. The address comes in the query string, set by the
 * register redirect, so the resend does not ask for it twice.
 */
export default function CheckEmailScreen() {
  const [params] = useSearchParams();
  const email = params.get("email") ?? "";
  const resend = useResendVerification();

  return (
    <div style={cardStyle}>
      <h1>Revisa tu correo</h1>
      <p>
        Te enviamos un enlace de verificación a <strong>{email}</strong>.
      </p>
      <p>Abre el enlace para activar tu cuenta.</p>
      <button
        type="button"
        onClick={() => resend.mutate({ email })}
        disabled={resend.isPending}
        style={{ width: "100%", padding: 10 }}
      >
        {resend.isPending ? "Enviando…" : "Reenviar correo"}
      </button>
      {resend.isSuccess && (
        <p role="status" style={{ color: "#2e7d32", marginTop: 12 }}>
          Correo enviado. Revisa tu bandeja de entrada.
        </p>
      )}
      <p style={{ marginTop: 16 }}>
        <Link to="/login">Volver a iniciar sesión</Link>
      </p>
    </div>
  );
}
