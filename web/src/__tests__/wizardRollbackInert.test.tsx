import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { readWizardFlags } from "../lib/wizardStorage";

// Same harness as wizardTrigger.test.tsx: render the real AppShell with its
// views/auth/events mocked so the test can run without a backend.
vi.mock("../routes/ChatView", () => ({ default: () => <div>Chat</div> }));
vi.mock("../routes/FilesView", () => ({ default: () => <div>Files</div> }));
vi.mock("../routes/SettingsView", () => ({ default: () => <div>Settings</div> }));
vi.mock("../routes/ArchiveList", () => ({ default: () => <div>Archives</div> }));

vi.mock("../queries/useAuth", () => ({
  useMe: () => ({ data: { id: 1, email: "test@test.com" }, isLoading: false, error: null }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// One existing session keeps the wizard trigger inert, isolating the app shell so
// any rendering change can only come from the leftover localStorage key.
vi.mock("../queries/useSessions", () => ({
  useSessions: () => ({
    data: [{ id: "ses-1", title: "Existing", created_at: "", updated_at: "" }],
    isLoading: false,
    isSuccess: true,
    isError: false,
  }),
}));

vi.mock("../queries/useFiles", () => ({
  useFilesGlobal: () => ({
    data: [],
    isLoading: false,
    isSuccess: true,
    isError: false,
    hasMore: false,
    loadMore: vi.fn(),
    isLoadingMore: false,
  }),
}));

vi.mock("../lib/useSessionEvents", () => ({ useSessionEvents: () => {} }));

import AppShell from "../routes/AppShell";

const STORAGE_KEY = "datara.wizard";

// Shapes a rollback could leave behind: a foreign/legacy payload, a truncated or
// malformed value, or a partial object the current writer never produces.
const leftoverPayloads: Array<[string, string]> = [
  ["foreign object", '{"foreign":"payload","count":3}'],
  ["legacy string", '"datara-wizard-v0"'],
  ["JSON null", "null"],
  ["JSON array", "[]"],
  ["JSON number", "123"],
  ["partial flags", '{"wizardComplete":true}'],
  ["malformed JSON", "{not-json"],
];

const renderShell = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/app/chat"]}>
        <Routes>
          <Route path="/app/*" element={<AppShell />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("wizard rollback: datara.wizard is inert", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it.each(leftoverPayloads)(
    "readWizardFlags returns safe defaults and never throws for a %s payload",
    (_label, payload) => {
      localStorage.setItem(STORAGE_KEY, payload);

      let flags: ReturnType<typeof readWizardFlags> | undefined;
      expect(() => {
        flags = readWizardFlags();
      }).not.toThrow();
      expect(flags).toEqual({ wizardComplete: false, wizardSkipped: false });
    },
  );

  it("renders the app shell normally with a leftover payload present", async () => {
    localStorage.setItem(STORAGE_KEY, '{"foreign":"payload"}');

    // The statically imported store initialised before this test, so this only
    // proves a foreign value sitting in localStorage does not break rendering or
    // leak into the app shell. The genuine boot-read proof is the next test.
    expect(() => renderShell()).not.toThrow();
    expect(screen.getByText("Datara")).toBeTruthy();
    // "Chat" appears both as a sidebar link and inside the lazily-resolved view;
    // awaiting it also wraps the suspension resolution in act().
    expect((await screen.findAllByText("Chat")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("dialog", { name: /first-run wizard/i })).toBeNull();
  });

  it("a fresh boot reads a leftover/foreign key as the safe default without throwing", async () => {
    // A real app boot re-evaluates the store initializer. Reset the module
    // registry and re-import AFTER seeding the key so the boot read is genuine;
    // the statically imported store above initialised long before this test.
    localStorage.setItem(STORAGE_KEY, '{"foreign":"payload","count":3}');
    vi.resetModules();
    const foreignBoot = await import("../stores/useWizardStore");
    expect(foreignBoot.useWizardStore.getState().dismissed).toBe(false);

    // Positive control: a valid "complete" payload DOES reach the freshly booted
    // store, so the assertion above proves the foreign value is inert rather than
    // the store simply ignoring localStorage.
    localStorage.setItem(
      STORAGE_KEY,
      '{"wizardComplete":true,"wizardSkipped":false}',
    );
    vi.resetModules();
    const validBoot = await import("../stores/useWizardStore");
    expect(validBoot.useWizardStore.getState().dismissed).toBe(true);
  });
});
