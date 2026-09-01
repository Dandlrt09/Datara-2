import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { useRegister } from "../queries/useAuth";
import { ApiError } from "../lib/api";

interface RegisterForm {
  email: string;
  password: string;
}

export default function RegisterScreen() {
  const navigate = useNavigate();
  const registerMut = useRegister();
  const { register, handleSubmit, formState: { errors } } = useForm<RegisterForm>();

  const onSubmit = async (data: RegisterForm) => {
    try {
      await registerMut.mutateAsync(data);
      navigate("/app/chat");
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
          <p style={{ color: "red" }}>
            {(registerMut.error as ApiError).status === 409
              ? "Email already registered"
              : "Registration failed"}
          </p>
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