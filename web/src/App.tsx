import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

const LoginScreen = lazy(() => import("./routes/LoginScreen"));
const RegisterScreen = lazy(() => import("./routes/RegisterScreen"));
const CheckEmailScreen = lazy(() => import("./routes/CheckEmailScreen"));
const VerifyEmailScreen = lazy(() => import("./routes/VerifyEmailScreen"));
const ForgotPasswordScreen = lazy(() => import("./routes/ForgotPasswordScreen"));
const ResetPasswordScreen = lazy(() => import("./routes/ResetPasswordScreen"));
const AppShell = lazy(() => import("./routes/AppShell"));
const TermsScreen = lazy(() => import("./routes/TermsScreen"));

function Loading() {
  return <div>Loading...</div>;
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/login" element={<LoginScreen />} />
        <Route path="/register" element={<RegisterScreen />} />
        {/* Email verification and password recovery (S3/S4). Both link targets
            are frontend routes, never the API: a mail prefetcher must not be
            able to consume a one-shot token (D9). */}
        <Route path="/check-email" element={<CheckEmailScreen />} />
        <Route path="/verify-email" element={<VerifyEmailScreen />} />
        <Route path="/forgot-password" element={<ForgotPasswordScreen />} />
        <Route path="/reset-password" element={<ResetPasswordScreen />} />
        <Route path="/terminos" element={<TermsScreen />} />
        <Route path="/app/*" element={<AppShell />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </Suspense>
  );
}