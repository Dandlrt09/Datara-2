import { describe, it, expect } from "vitest";
import { api, ApiError } from "../lib/api";

const { fetch } = globalThis;

describe("ApiError", () => {
  it("creates an error with status and body", () => {
    const err = new ApiError(401, { detail: "Unauthorized" });
    expect(err.status).toBe(401);
    expect(err.body).toEqual({ detail: "Unauthorized" });
    expect(err.message).toContain("401");
  });
});

describe("api.get", () => {
  it("sends credentials and parses JSON", async () => {
    globalThis.fetch = async (url: RequestInfo | URL, init?: RequestInit) => {
      expect((init as RequestInit)?.credentials).toBe("include");
      return new Response(JSON.stringify({ id: 1, email: "test@test.com" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    const result = await api.get<{ id: number; email: string }>("/api/sessions");
    expect(result.id).toBe(1);
    expect(result.email).toBe("test@test.com");

    globalThis.fetch = fetch;
  });

  it("throws ApiError on non-ok response", async () => {
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ detail: "Forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });

    await expect(api.get("/api/sessions")).rejects.toThrow(ApiError);

    globalThis.fetch = fetch;
  });
});

describe("api.post", () => {
  it("sends JSON body", async () => {
    globalThis.fetch = async (_url: RequestInfo | URL, init?: RequestInit) => {
      const body = (init as RequestInit)?.body as string;
      expect(JSON.parse(body)).toEqual({ email: "a@b.com", password: "p" });
      expect((init as RequestInit)?.method).toBe("POST");
      return new Response(JSON.stringify({ id: 1 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    const result = await api.post("/api/auth/login", { email: "a@b.com", password: "p" });
    expect(result).toEqual({ id: 1 });

    globalThis.fetch = fetch;
  });
});

describe("api.delete", () => {
  it("returns undefined for 204", async () => {
    globalThis.fetch = async () => new Response(null, { status: 204 });

    const result = await api.delete("/api/sessions/abc");
    expect(result).toBeUndefined();

    globalThis.fetch = fetch;
  });
});