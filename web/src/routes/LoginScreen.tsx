import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useLogin } from "../queries/useAuth";
import { ApiError } from "../lib/api";

interface LoginForm {
  email: string;
  password: string;
}

export default function LoginScreen() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useLogin();
  const { register, handleSubmit, formState: { errors } } = useForm<LoginForm>();

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
          <p style={{ color: "red" }}>
            {(login.error as ApiError).status === 401
              ? "Invalid credentials"
              : "Login failed"}
          </p>
        )}
        <button type="submit" disabled={login.isPending} style={{ width: "100%", padding: 10 }}>
          {login.isPending ? "Logging in..." : "Log in"}
        </button>
      </form>
      <p style={{ marginTop: 16 }}>
        Don't have an account? <Link to="/register">Register</Link>
      </p>
    </div>
  );
}