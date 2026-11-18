import { lazy, Suspense, type ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useDataFolder } from "./queries/useDataFolder";

const DataFolderScreen = lazy(() => import("./routes/DataFolderScreen"));
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

/**
 * First-run gate (S1/S5): until the analyst decides where the data lives, the
 * data-folder screen is the only thing they see, before login or registration.
 *
 * A failed probe falls through to the normal routes so a backend hiccup cannot
 * brick the app; the picker is a first-run convenience, not an auth gate.
 */
function DataFolderGate({ children }: { children: ReactNode }) {
  const { data, isError } = useDataFolder();
  const queryClient = useQueryClient();

  if (isError || data?.decided) return <>{children}</>;
  if (!data) return <Loading />;

  return (
    <DataFolderScreen
      currentPath={data.path}
      defaultPath={data.default_path}
      onContinue={() => {
        void queryClient.invalidateQueries({ queryKey: ["data-folder"] });
      }}
    />
  );
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <DataFolderGate>
        <Routes>
          <Route path="/login" element={<LoginScreen />} />
          <Route path="/register" element={<RegisterScreen />} />
          {/* Email verification and password recovery (S3/S4). Both link
              targets are frontend routes, never the API: a mail prefetcher
              must not be able to consume a one-shot token (D9). */}
          <Route path="/check-email" element={<CheckEmailScreen />} />
          <Route path="/verify-email" element={<VerifyEmailScreen />} />
          <Route path="/forgot-password" element={<ForgotPasswordScreen />} />
          <Route path="/reset-password" element={<ResetPasswordScreen />} />
          <Route path="/terminos" element={<TermsScreen />} />
          <Route path="/app/*" element={<AppShell />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </DataFolderGate>
    </Suspense>
  );
}