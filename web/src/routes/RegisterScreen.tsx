import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { useRegister } from "../queries/useAuth";
import { ApiError } from "../lib/api";

interface RegisterForm {
  email: string;
  password: string;
}

/**
 * Turn the register error into the line the person reads.
 *
 * 409 and 422 are states the server actually distinguishes, and 429 is the new
 * attempt brake (S3): without a case here the user would see "Registration
 * failed" while the account is fine and they merely have to wait.
 */
function registerErrorMessage(error: unknown): string {
  switch ((error as ApiError).status) {
    case 409:
      return "Email already registered";
    case 422:
      return "Revisá los datos ingresados";
    case 429:
      return "Demasiados intentos, probá más tarde";
    default:
      return "Registration failed";
  }
}

export default function RegisterScreen() {
  const navigate = useNavigate();
  const registerMut = useRegister();
  const { register, handleSubmit, formState: { errors } } = useForm<RegisterForm>();

  const onSubmit = async (data: RegisterForm) => {
    try {
      await registerMut.mutateAsync(data);
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
      <h2>Register</h2>
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
            {...register("password", {
              required: "Password is required",
              minLength: { value: 8, message: "At least 8 characters" },
            })}
            type="password"
            placeholder="Password (8+ characters)"
            style={{ width: "100%", padding: 8 }}
          />
          {errors.password && <p style={{ color: "red" }}>{errors.password.message}</p>}
        </div>
        {registerMut.error && (
          <p style={{ color: "red" }}>{registerErrorMessage(registerMut.error)}</p>
        )}
        <button type="submit" disabled={registerMut.isPending} style={{ width: "100%", padding: 10 }}>
          {registerMut.isPending ? "Registering..." : "Register"}
        </button>
      </form>
      <p style={{ marginTop: 16 }}>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </div>
  );
}