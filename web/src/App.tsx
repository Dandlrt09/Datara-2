import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

const LoginScreen = lazy(() => import("./routes/LoginScreen"));
const RegisterScreen = lazy(() => import("./routes/RegisterScreen"));
const AppShell = lazy(() => import("./routes/AppShell"));

function Loading() {
  return <div>Loading...</div>;
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/login" element={<LoginScreen />} />
        <Route path="/register" element={<RegisterScreen />} />
        <Route path="/app/*" element={<AppShell />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </Suspense>
  );
}