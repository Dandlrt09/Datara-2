import { lazy, Suspense, type ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useDataFolder } from "./queries/useDataFolder";
import { emailFlowsEnabled, useAppConfig } from "./queries/useAppConfig";

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

/**
 * Email-flow gate (F1 / T1, D2/D6): in ``local`` mode there is no email, so the
 * registration / verification / recovery screens are not routed -- they stay in
 * the code for the hosted deployment. While the mode loads nothing renders (no
 * flash of a screen that is about to disappear); if it cannot be read the
 * screens stay reachable, as before.
 */
function HostedOnly({ children }: { children: ReactNode }) {
  const config = useAppConfig();

  if (!config.data && !config.isError) return <Loading />;
  if (!emailFlowsEnabled(config)) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <DataFolderGate>
        <Routes>
          <Route path="/login" element={<LoginScreen />} />
          <Route
            path="/register"
            element={
              <HostedOnly>
                <RegisterScreen />
              </HostedOnly>
            }
          />
          {/* Email verification and password recovery (S3/S4). Both link
              targets are frontend routes, never the API: a mail prefetcher
              must not be able to consume a one-shot token (D9). */}
          <Route
            path="/check-email"
            element={
              <HostedOnly>
                <CheckEmailScreen />
              </HostedOnly>
            }
          />
          <Route
            path="/verify-email"
            element={
              <HostedOnly>
                <VerifyEmailScreen />
              </HostedOnly>
            }
          />
          <Route
            path="/forgot-password"
            element={
              <HostedOnly>
                <ForgotPasswordScreen />
              </HostedOnly>
            }
          />
          <Route
            path="/reset-password"
            element={
              <HostedOnly>
                <ResetPasswordScreen />
              </HostedOnly>
            }
          />
          <Route path="/terminos" element={<TermsScreen />} />
          <Route path="/app/*" element={<AppShell />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </DataFolderGate>
    </Suspense>
  );
}