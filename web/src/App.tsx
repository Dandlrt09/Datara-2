import { lazy, Suspense, useRef, type ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useDataFolder } from "./queries/useDataFolder";
import { emailFlowsEnabled, useAppConfig } from "./queries/useAppConfig";

const DataFolderScreen = lazy(() => import("./routes/DataFolderScreen"));
const FirstRunScreen = lazy(() => import("./routes/FirstRunScreen"));
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
 * The restart notice shown after the analyst picks a new data folder in the
 * same boot (L12). The chosen folder only takes effect on the next boot -- the
 * server resolves the store path once at import and never re-opens it -- so
 * letting the app continue here would create the profile in the old database
 * and orphan the first row after the restart. There is no honest way to apply
 * the choice in place: `window.location.reload()` reloads the SPA but does not
 * re-open the store either.
 */
function RestartNotice() {
  return (
    <div style={{ maxWidth: 400, margin: "80px auto", padding: 24 }}>
      <h1>Reinicia Datara</h1>
      <p role="status">
        Cierra Datara y vuelve a abrirla. Elegiste una carpeta nueva y se usa a
        partir del próximo arranque. Si sigues ahora, tu perfil se guardaría en
        la carpeta anterior.
      </p>
    </div>
  );
}

/**
 * First-run gate (S1/S5): until the analyst decides where the data lives, the
 * data-folder screen is the only thing they see, before login or registration.
 *
 * A failed probe falls through to the normal routes so a backend hiccup cannot
 * brick the app; the picker is a first-run convenience, not an auth gate.
 *
 * Once this boot has seen the folder undecided, deciding it does not release
 * the app: the choice applies next boot, so the analyst gets the restart notice
 * instead (L12). The ref is a latch, because React Query has no `staleTime`
 * here and a later refetch or window focus would otherwise fall back into the
 * same boot.
 */
function DataFolderGate({ children }: { children: ReactNode }) {
  const { data, isError } = useDataFolder();
  const queryClient = useQueryClient();
  // Reflects whether this boot ever saw the folder undecided.
  const sawUndecided = useRef(false);

  if (data && !data.decided) sawUndecided.current = true;

  // Evaluated first (D1/S1): once this boot saw the folder undecided, only an
  // explicitly undecided read releases the app. A decided refetch and an
  // erroring or undefined refetch all keep the notice, so a failed probe
  // cannot reopen the app in the boot that chose the folder.
  if (sawUndecided.current && data?.decided !== false) {
    return <RestartNotice />;
  }
  if (isError) return <>{children}</>;
  if (data?.decided) return <>{children}</>;
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

/**
 * Where an unauthenticated visitor lands (F1 / T2c). In local mode there is no
 * login, so the front door is the first-run screen; hosted keeps sending to
 * login. The mode is read before deciding, and an unreadable mode falls back
 * to login, the same fail-open rule `HostedOnly` uses (T1).
 */
function UnauthenticatedLanding() {
  const config = useAppConfig();

  if (!config.data && !config.isError) return <Loading />;
  return (
    <Navigate to={emailFlowsEnabled(config) ? "/login" : "/first-run"} replace />
  );
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <DataFolderGate>
        <Routes>
          {/* Local-mode identity (F1 / T2c): outside `HostedOnly` (it would
              bounce to /login) and outside /app (AppShell's guard would too),
              but inside the F3b data-folder gate, which runs first. */}
          <Route path="/first-run" element={<FirstRunScreen />} />
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
          <Route path="*" element={<UnauthenticatedLanding />} />
        </Routes>
      </DataFolderGate>
    </Suspense>
  );
}