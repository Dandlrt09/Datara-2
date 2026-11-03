import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import { useRegister } from "../queries/useAuth";
import { TERMS_VERSION } from "../lib/terms";

vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const USER = { id: 1, email: "dan@example.com", name: null, pending_deletion_at: null };

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function wrapperFor(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useRegister", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("posts the optional name along with the credentials", async () => {
    (api.post as Mock).mockResolvedValue(USER);
    const client = makeClient();
    const { result } = renderHook(() => useRegister(), {
      wrapper: wrapperFor(client),
    });

    await result.current.mutateAsync({
      email: "dan@example.com",
      password: "password123",
      name: "Daniel",
      terms_version: TERMS_VERSION,
    });

    expect(api.post).toHaveBeenCalledWith("/api/auth/register", {
      email: "dan@example.com",
      password: "password123",
      name: "Daniel",
      terms_version: TERMS_VERSION,
    });
  });

  it("does not open a session: no me-cache write, no session invalidation (D4)", async () => {
    (api.post as Mock).mockResolvedValue(USER);
    const client = makeClient();
    const setData = vi.spyOn(client, "setQueryData");
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useRegister(), {
      wrapper: wrapperFor(client),
    });

    await result.current.mutateAsync({
      email: "dan@example.com",
      password: "password123",
      terms_version: TERMS_VERSION,
    });

    // Register no longer authenticates (D4): there is no session to cache and
    // nothing to invalidate, so the mutation stays side-effect free.
    expect(setData).not.toHaveBeenCalled();
    expect(invalidate).not.toHaveBeenCalled();
  });
});
