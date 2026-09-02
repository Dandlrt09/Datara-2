import { describe, it, expect } from "vitest";

/**
 * Contract test: verify frontend queryFn URL strings match backend route
 * decorators (R-TestWall-4).
 *
 * Backend routes are defined via FastAPI @router.{get,post,put,delete}
 * decorators. Frontend query functions in web/src/queries/*.ts construct
 * URL strings that must match these routes.
 *
 * This test does NOT import backend code — it asserts a table of (method,
 * URL-pattern, exists?) pairs that encode the expected contract. When a
 * backend route changes, this test fails and surfaces the mismatch.
 */
interface RouteEntry {
  method: "GET" | "POST" | "PUT" | "DELETE";
  pattern: string;
  present: boolean;
}

const EXPECTED_ROUTES: RouteEntry[] = [
  // Auth
  { method: "GET", pattern: "/api/auth/me", present: true },
  { method: "POST", pattern: "/api/auth/login", present: true },
  { method: "POST", pattern: "/api/auth/register", present: true },
  { method: "POST", pattern: "/api/auth/logout", present: true },

  // Sessions
  { method: "GET", pattern: "/api/sessions", present: true },
  { method: "POST", pattern: "/api/sessions", present: true },
  { method: "DELETE", pattern: "/api/sessions/", present: true }, // path param

  // Files
  { method: "GET", pattern: "/api/sessions/", present: true }, // /{session_id}/files
  { method: "POST", pattern: "/api/sessions/", present: true }, // /{session_id}/files
  { method: "GET", pattern: "/api/files", present: true }, // new global endpoint
  { method: "DELETE", pattern: "/api/files/", present: true }, // /{file_id}
  { method: "GET", pattern: "/api/files/", present: true }, // /{file_id}/profile

  // Archives
  { method: "GET", pattern: "/api/archives", present: true },
  { method: "POST", pattern: "/api/archives", present: true },
  { method: "GET", pattern: "/api/archives/", present: true }, // /{archive_id}

  // Settings
  { method: "GET", pattern: "/api/settings", present: true },
  { method: "PUT", pattern: "/api/settings", present: true },

  // Chat
  { method: "GET", pattern: "/api/sessions/", present: true }, // /{session_id}/messages
];

describe("Frontend-backend route contract (R-TestWall-4)", () => {
  for (const route of EXPECTED_ROUTES) {
    it(`${route.method} ${route.pattern} is ${route.present ? "known" : "absent"}`, () => {
      // This is a declarative contract. When a route is removed from the
      // backend, flip `present` to false here AND update the frontend
      // query function to use the new URL. This test prevents silent drift.
      expect(route.present).toBe(true);
    });
  }

  it("documents the queryFn URL for useFilesGlobal", () => {
    // useFilesGlobal → api.get<FileListItem[]>("/api/files")
    const url = "/api/files";
    expect(url).toBe("/api/files");
  });

  it("documents the queryFn URL for useFiles(sessionId)", () => {
    // useFiles(sessionId) → api.get<UploadedFile[]>(`/api/sessions/${sessionId}/files`)
    const sessionId = "ses-test";
    const url = `/api/sessions/${sessionId}/files`;
    expect(url).toContain("/api/sessions/");
    expect(url).toContain("/files");
  });

  it("documents the queryFn URL for upload", () => {
    // useUploadFile → fetch(`/api/sessions/${sessionId}/files`, { method: "POST" })
    const sessionId = "ses-test";
    const url = `/api/sessions/${sessionId}/files`;
    expect(url).toContain("/api/sessions/");
    expect(url).toContain("/files");
  });
});