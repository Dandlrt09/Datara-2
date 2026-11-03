import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useVerifyEmail } from "../queries/useAuth";

const cardStyle = { maxWidth: 400, margin: "80px auto", padding: 24 };

/**
 * Redeem the emailed verification token (S3/D9/D10).
 *
 * The mail links here with the token in the query string; the screen fires the
 * POST once. The effect guard keeps a re-render from redeeming the one-shot
 * token a second time. Verifying does not log anyone in: on success the screen
 * confirms and points at login.
 */
export default function VerifyEmailScreen() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const verify = useVerifyEmail();
  const started = useRef(false);

  useEffect(() => {
    if (started.current || !token) return;
    started.current = true;
    verify.mutate({ token });
  }, [token, verify]);

  if (!token || verify.isError) {
    return (
      <div style={cardStyle}>
        <h1>El enlace no es válido o ya venció</h1>
        <p>Pide un enlace nuevo e inténtalo otra vez.</p>
        <p style={{ marginTop: 16 }}>
          <Link to="/login">Ir a iniciar sesión</Link>
        </p>
      </div>
    );
  }

  if (verify.isSuccess) {
    return (
      <div style={cardStyle}>
        <h1>Correo verificado</h1>
        <p>Tu correo quedó verificado. Ya puedes iniciar sesión.</p>
        <p style={{ marginTop: 16 }}>
          <Link to="/login">Ir a iniciar sesión</Link>
        </p>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <h1>Verificando tu correo…</h1>
    </div>
  );
}
