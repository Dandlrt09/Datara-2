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

  it("drops the stale chat-session list, like login does (D5)", async () => {
    (api.post as Mock).mockResolvedValue(USER);
    const client = makeClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useRegister(), {
      wrapper: wrapperFor(client),
    });

    await result.current.mutateAsync({
      email: "dan@example.com",
      password: "password123",
      terms_version: TERMS_VERSION,
    });

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["sessions"] });
  });
});
