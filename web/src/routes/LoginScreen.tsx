import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useLogin, useResendVerification } from "../queries/useAuth";
import { ApiError } from "../lib/api";

interface LoginForm {
  email: string;
  password: string;
}

/**
 * Turn the login error into the line the person reads.
 *
 * 429 is the attempt brake (S3); without it the user would read "Login failed"
 * and keep retrying a door the server is holding shut on purpose.
 */
function loginErrorMessage(error: unknown): string {
  switch ((error as ApiError).status) {
    case 401:
      return "Invalid credentials";
    case 403:
      // Correct password, unverified address (D5): the gate the person can
      // open from here by resending the verification mail.
      return "Your email is not verified yet";
    case 429:
      return "Demasiados intentos, probá más tarde";
    default:
      return "Login failed";
  }
}

export default function LoginScreen() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useLogin();
  const resend = useResendVerification();
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<LoginForm>();

  // The resend needs the address the person just typed, so watch the field
  // instead of asking for it twice.
  const email = watch("email");
  const emailNotVerified = (login.error as ApiError | null)?.status === 403;

  // A deletion request lands here with a one-shot notice (S5); the exact purge
  // date is shown on the interstitial after signing in (S7).
  const notice = (location.state as { notice?: string } | null)?.notice;

  const onSubmit = async (data: LoginForm) => {
    try {
      await login.mutateAsync(data);
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
      <h2>Log in</h2>
      {notice && (
        <p
          role="status"
          style={{
            background: "#fff8f7",
            border: "1px solid #f2b8b5",
            color: "#c62828",
            padding: 12,
            borderRadius: 6,
            marginBottom: 16,
          }}
        >
          {notice}
        </p>
      )}
      <form onSubmit={handleSubmit(onSubmit)}>
        <div style={{ marginBottom: 16 }}>
          <input
            {...register("email", { required: "Email is required" })}
            type="email"
            placeholder="Email"
            style={{ width: "100%", padding: 8 }}
          />
          {errors.email && <p style={{ color: "red" }}>{errors.email.message}</p>}
        </div>
        <div style={{ marginBottom: 16 }}>
          <input
            {...register("password", { required: "Password is required" })}
            type="password"
            placeholder="Password"
            style={{ width: "100%", padding: 8 }}
          />
          {errors.password && <p style={{ color: "red" }}>{errors.password.message}</p>}
        </div>
        {login.error && (
          <p style={{ color: "red" }}>{loginErrorMessage(login.error)}</p>
        )}
        {emailNotVerified && (
          <div style={{ marginBottom: 16 }}>
            <button
              type="button"
              onClick={() => resend.mutate({ email: email ?? "" })}
              disabled={resend.isPending}
              style={{ padding: 8 }}
            >
              Reenviar correo
            </button>
            {resend.isSuccess && (
              <p role="status" style={{ color: "#2e7d32", marginTop: 8 }}>
                Verification email sent
              </p>
            )}
          </div>
        )}
        <button type="submit" disabled={login.isPending} style={{ width: "100%", padding: 10 }}>
          {login.isPending ? "Logging in..." : "Log in"}
        </button>
      </form>
      <p style={{ marginTop: 16 }}>
        <Link to="/forgot-password">Forgot your password?</Link>
      </p>
      <p style={{ marginTop: 16 }}>
        Don't have an account? <Link to="/register">Register</Link>
      </p>
    </div>
  );
}