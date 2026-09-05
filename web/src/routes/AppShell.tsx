import { lazy, Suspense, useEffect, useCallback } from "react";
import { Routes, Route, useNavigate, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useMe, useLogout } from "../queries/useAuth";
import { RouteErrorBoundary } from "../components/ErrorCard";
import { useSessionEvents, type SessionEvent } from "../lib/useSessionEvents";
import type { ChatSession } from "../queries/useSessions";

const ChatView = lazy(() => import("./ChatView"));
const FilesView = lazy(() => import("./FilesView"));
const SettingsView = lazy(() => import("./SettingsView"));
const ArchiveList = lazy(() => import("./ArchiveList"));

function Loading() {
  return <div>Loading...</div>;
}

function NotFound() {
  return (
    <div style={{ textAlign: "center", marginTop: 80 }}>
      <h2>404</h2>
      <p>This page does not exist.</p>
      <Link to="/app/chat">Back to Chat</Link>
    </div>
  );
}

function withErrorBoundary(viewName: string, Element: React.ComponentType) {
  return (
    <RouteErrorBoundary viewName={viewName}>
      <Element />
    </RouteErrorBoundary>
  );
}

export default function AppShell() {
  const navigate = useNavigate();
  const { data: user, isLoading, error } = useMe();
  const logout = useLogout();
  const queryClient = useQueryClient();

  const onEvent = useCallback(
    (event: SessionEvent) => {
      // Cancel in-flight refetches before patching to avoid race conditions
      queryClient.cancelQueries({ queryKey: ["sessions"] });
      queryClient.setQueryData<ChatSession[]>(["sessions"], (old) => {
        if (!old) return old;
        switch (event.type) {
          case "session.created":
          case "session.updated":
            return old.map((s) =>
              s.id === event.session_id ? { ...s, ...event.payload } : s,
            );
          case "session.titled":
            return old.map((s) =>
              s.id === event.session_id
                ? { ...s, title: (event.payload.title as string) ?? s.title }
                : s,
            );
          case "session.deleted":
            return old.filter((s) => s.id !== event.session_id);
          case "session.streaming_started":
            return old.map((s) =>
              s.id === event.session_id ? { ...s, is_streaming: true } : s,
            );
          case "session.streaming_ended":
            return old.map((s) =>
              s.id === event.session_id ? { ...s, is_streaming: false } : s,
            );
          default:
            return old;
        }
      });
    },
    [queryClient],
  );

  const onReconnected = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["sessions"] });
  }, [queryClient]);

  useSessionEvents({ onEvent, onReconnected });

  useEffect(() => {
    if (!isLoading && (error || !user)) {
      navigate("/login", { replace: true });
    }
  }, [user, isLoading, error, navigate]);

  if (isLoading) return <div>Checking auth...</div>;
  if (!user) return null;

  const handleLogout = async () => {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  };

  return (
    <div style={{ display: "flex", height: "100vh" }}>
      {/* Sidebar */}
      <nav
        style={{
          width: 220,
          background: "#f8f9fa",
          padding: 16,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <h2 style={{ margin: "0 0 16px" }}>Datara</h2>
        <Link to="/app/chat" style={{ marginBottom: 8 }}>
          Chat
        </Link>
        <Link to="/app/files" style={{ marginBottom: 8 }}>
          Files
        </Link>
        <Link to="/app/archives" style={{ marginBottom: 8 }}>
          Archives
        </Link>
        <Link to="/app/settings" style={{ marginBottom: 8 }}>
          Settings
        </Link>
        <div style={{ marginTop: "auto" }}>
          <p style={{ fontSize: "0.85em", color: "#666" }}>{user.email}</p>
          <button onClick={handleLogout} disabled={logout.isPending}>
            Log out
          </button>
        </div>
      </nav>

      {/* Main content */}
      <main style={{ flex: 1, overflow: "auto", padding: 24 }}>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route
              path="/chat/:sessionId?"
              element={withErrorBoundary("Chat", ChatView)}
            />
            <Route
              path="/files"
              element={withErrorBoundary("Files", FilesView)}
            />
            <Route
              path="/settings"
              element={withErrorBoundary("Settings", SettingsView)}
            />
            <Route
              path="/archives"
              element={withErrorBoundary("Archives", ArchiveList)}
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}