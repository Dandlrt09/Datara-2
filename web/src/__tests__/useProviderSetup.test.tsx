import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  saveErrorMessage,
  useProviderSetup,
  type ProviderForm,
} from "../routes/settings/useProviderSetup";
import { COPY } from "../routes/setup/copy";
import { RECOMMENDED_MODELS } from "../routes/settings/recommended";

const { useSettingsMock, mutateMock, fetchModelsMock, useFetchModelsMock } = vi.hoisted(
  () => ({
    useSettingsMock: vi.fn(),
    mutateMock: vi.fn(),
    fetchModelsMock: vi.fn(),
    useFetchModelsMock: vi.fn(),
  })
);

vi.mock("../queries/useSettings", () => ({
  useSettings: () => useSettingsMock(),
  useUpdateSettings: () => ({ mutateAsync: mutateMock, isPending: false }),
}));

vi.mock("../routes/setup/useFetchModels", () => ({
  useFetchModels: () => useFetchModelsMock(),
}));

const baseSettings = {
  user_id: 1,
  has_api_key: false,
  default_model: null,
  // Mirrors the shipped whitelist: base models + the recommended catalog.
  allowed_models: ["gpt-4o", "gpt-4o-mini", ...RECOMMENDED_MODELS.map((m) => m.model)],
  provider_type: null,
  base_url: null,
};

let queryClient: QueryClient;

function setupMocks(settingsOverrides: Record<string, unknown> = {}, models: unknown[] = []) {
  useSettingsMock.mockReset();
  mutateMock.mockReset();
  fetchModelsMock.mockReset();
  useFetchModelsMock.mockReset();

  useSettingsMock.mockReturnValue({
    data: { ...baseSettings, ...settingsOverrides },
    isLoading: false,
  });
  mutateMock.mockResolvedValue({ ...baseSettings, ...settingsOverrides });
  fetchModelsMock.mockResolvedValue({ models, error: null });
  useFetchModelsMock.mockReturnValue({
    models,
    isLoading: false,
    error: null,
    fetchModels: fetchModelsMock,
  });
}

function renderEngine() {
  return renderHook(() => useProviderSetup(), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

function blankForm(overrides: Partial<ProviderForm> = {}): ProviderForm {
  return { provider_type: "", base_url: "", api_key: "", default_model: "", ...overrides };
}

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  setupMocks();
});

describe("useProviderSetup — prefill", () => {
  it("prefills the saved provider and its saved url", async () => {
    setupMocks({
      provider_type: "openrouter",
      base_url: "https://gateway.example.com/v1",
      default_model: "gpt-4o",
      has_api_key: true,
    });
    const { result } = renderEngine();

    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));
    expect(result.current.values.base_url).toBe("https://gateway.example.com/v1");
    expect(result.current.values.default_model).toBe("gpt-4o");
    // The key never comes back from the server.
    expect(result.current.values.api_key).toBe("");
  });

  it("fills the preset default url when nothing was saved", async () => {
    setupMocks({ provider_type: "ollama", base_url: null });
    const { result } = renderEngine();

    await waitFor(() => expect(result.current.values.provider_type).toBe("ollama"));
    expect(result.current.values.base_url).toBe("http://localhost:11434/v1");
  });

  it("keeps a stored provider that no preset carries and offers it (S4)", async () => {
    setupMocks({
      provider_type: "mistral",
      base_url: "https://api.mistral.ai/v1",
      has_api_key: true,
    });
    const { result } = renderEngine();

    await waitFor(() => expect(result.current.values.provider_type).toBe("mistral"));
    const legacy = result.current.providerOptions.find((o) => o.id === "mistral");
    expect(legacy?.legacy).toBe(true);
    expect(legacy?.label).toBe(COPY.LEGACY_PROVIDER_LABEL("mistral"));
    // Five presets plus the stored value: nothing is silently dropped.
    expect(result.current.providerOptions).toHaveLength(6);
    expect(result.current.preset?.id).toBe("mistral");
  });
});

describe("useProviderSetup — switching provider", () => {
  it("resets base_url to the new preset default and clears the model", async () => {
    setupMocks({ provider_type: "openrouter", default_model: "gpt-4o" });
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));

    act(() => result.current.chooseProvider("ollama"));

    expect(result.current.values.base_url).toBe("http://localhost:11434/v1");
    expect(result.current.values.default_model).toBe("");
    expect(result.current.preset?.id).toBe("ollama");
  });
});

describe("useProviderSetup — validation", () => {
  it("requires a provider before anything else", () => {
    const { result } = renderEngine();
    expect(result.current.validateProvider(blankForm())).toBe(COPY.PROVIDER_REQUIRED);
    expect(result.current.validateCredentials(blankForm())).toBe(COPY.PROVIDER_REQUIRED);
  });

  it("requires a base url only for the custom provider", () => {
    const { result } = renderEngine();
    const custom = blankForm({ provider_type: "custom", api_key: "sk-1" });
    expect(result.current.validateCredentials(custom)).toBe(COPY.BASE_URL_REQUIRED);
    expect(
      result.current.validateCredentials({ ...custom, base_url: "https://x.example.com/v1" }),
    ).toBeNull();
  });

  it("requires an api key only when the server holds none", () => {
    setupMocks({ has_api_key: true });
    const { result: withStoredKey } = renderEngine();
    expect(
      withStoredKey.current.validateCredentials(blankForm({ provider_type: "openrouter" })),
    ).toBeNull();

    setupMocks({ has_api_key: false });
    const { result: withoutKey } = renderEngine();
    expect(
      withoutKey.current.validateCredentials(blankForm({ provider_type: "openrouter" })),
    ).toBe(COPY.KEY_REQUIRED);
  });

  it("never asks a key from a keyless provider", () => {
    const { result } = renderEngine();
    expect(
      result.current.validateCredentials(blankForm({ provider_type: "lmstudio" })),
    ).toBeNull();
  });

  it("rejects a restricted model outside the whitelist", async () => {
    setupMocks({ provider_type: "openrouter", has_api_key: true });
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));

    expect(
      result.current.validateModel(blankForm({ provider_type: "openrouter" })),
    ).toBe(COPY.MODEL_REQUIRED);
    expect(
      result.current.validateModel(
        blankForm({ provider_type: "openrouter", default_model: "openai/not-whitelisted" }),
      ),
    ).toBe(COPY.MODEL_NOT_ALLOWED);
    expect(
      result.current.validateModel(
        blankForm({ provider_type: "openrouter", default_model: "gpt-4o" }),
      ),
    ).toBeNull();
  });

  it("accepts any model on an unrestricted provider", () => {
    const { result } = renderEngine();
    expect(
      result.current.validateModel(
        blankForm({ provider_type: "ollama", default_model: "mi-modelo:latest" }),
      ),
    ).toBeNull();
  });

  it("does not dead-end when the whitelist is unknown", async () => {
    setupMocks({ provider_type: "openrouter", has_api_key: true, allowed_models: [] });
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));

    expect(
      result.current.validateModel(
        blankForm({ provider_type: "openrouter", default_model: "cualquiera" }),
      ),
    ).toBeNull();
  });
});

describe("useProviderSetup — live model list", () => {
  const live = [
    { id: "gpt-4o", name: "GPT-4o" },
    { id: "openai/not-whitelisted", name: "Not Whitelisted" },
  ];

  it("filters a restricted provider's list by the whitelist", async () => {
    setupMocks({ provider_type: "openrouter", has_api_key: true }, live);
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));

    expect(result.current.isRestricted).toBe(true);
    expect(result.current.visibleModels.map((m) => m.id)).toEqual(["gpt-4o"]);
  });

  it("offers the full list to an unrestricted provider and filters by query", async () => {
    setupMocks({ provider_type: "groq", has_api_key: true }, live);
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("groq"));

    expect(result.current.isRestricted).toBe(false);
    expect(result.current.visibleModels).toHaveLength(2);

    act(() => result.current.setModelQuery("WHITELISTED"));
    expect(result.current.visibleModels.map((m) => m.id)).toEqual([
      "openai/not-whitelisted",
    ]);
  });
});

describe("useProviderSetup — honest save lifecycle", () => {
  it("saves first and probes after, claiming Connected only on a good probe", async () => {
    setupMocks({ provider_type: "openrouter", has_api_key: false });
    mutateMock.mockResolvedValue({ ...baseSettings, provider_type: "openrouter" });
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));
    act(() => {
      result.current.form.setValue("api_key", "sk-new");
      result.current.form.setValue("default_model", "gpt-4o");
    });

    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.persistAndProbe("all");
    });

    expect(outcome).toMatchObject({ ok: true });
    expect(mutateMock).toHaveBeenCalledWith({
      provider_type: "openrouter",
      base_url: "https://openrouter.ai/api/v1",
      api_key: "sk-new",
      default_model: "gpt-4o",
    });
    expect(fetchModelsMock).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("connected");
    expect(result.current.statusDetail).toBeNull();
  });

  it("reports the probe failure instead of pretending success", async () => {
    setupMocks({ provider_type: "openrouter", has_api_key: true });
    fetchModelsMock.mockResolvedValue({
      models: [],
      error: { code: "timeout", message: "sin respuesta" },
    });
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));
    act(() => result.current.form.setValue("default_model", "gpt-4o"));

    await act(async () => {
      await result.current.persistAndProbe("model");
    });

    expect(result.current.status).toBe("saved-unverified");
    expect(result.current.statusDetail).toBe("sin respuesta");
  });

  it("does not probe when the provider was cleared", async () => {
    setupMocks({ provider_type: "openrouter", has_api_key: true });
    mutateMock.mockResolvedValue({ ...baseSettings, provider_type: null });
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));
    act(() => result.current.chooseProvider(""));

    await act(async () => {
      await result.current.persistAndProbe("credentials");
    });

    expect(result.current.status).toBe("saved");
    expect(fetchModelsMock).not.toHaveBeenCalled();
  });

  it("reports a failed save and never probes", async () => {
    setupMocks({ provider_type: "custom", has_api_key: false });
    mutateMock.mockRejectedValue({
      body: { detail: { code: "invalid_base_url", message: "blocked" } },
    });
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("custom"));

    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.persistAndProbe("credentials");
    });

    expect(outcome).toEqual({ ok: false, message: COPY.SSRF_REJECTION });
    expect(result.current.status).toBe("save-error");
    expect(result.current.statusDetail).toBe(COPY.SSRF_REJECTION);
    expect(fetchModelsMock).not.toHaveBeenCalled();
  });

  it("maps the three FastAPI detail shapes to a user-readable reason", () => {
    expect(saveErrorMessage({ body: { detail: "boom" } })).toBe("boom");
    expect(saveErrorMessage({ body: { detail: [{ msg: "bad input" }] } })).toBe("bad input");
    expect(saveErrorMessage(new Error("network down"))).toBe("network down");
    expect(saveErrorMessage(undefined)).toBe("unknown error");
  });
});

describe("useProviderSetup — payload scoping", () => {
  it("omits the key and the model when saving credentials only", async () => {
    setupMocks({ provider_type: "openrouter", has_api_key: false });
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));
    act(() => result.current.form.setValue("default_model", "gpt-4o"));

    await act(async () => {
      await result.current.persist("credentials");
    });

    expect(mutateMock).toHaveBeenCalledWith({
      provider_type: "openrouter",
      base_url: "https://openrouter.ai/api/v1",
    });
    // The server holds the key now; the field must not keep it.
    expect(result.current.values.api_key).toBe("");
  });

  it("omits the provider when saving the model only", async () => {
    setupMocks({ provider_type: "openrouter", has_api_key: true });
    const { result } = renderEngine();
    await waitFor(() => expect(result.current.values.provider_type).toBe("openrouter"));
    act(() => result.current.form.setValue("default_model", "gpt-4o"));

    await act(async () => {
      await result.current.persist("model");
    });

    expect(mutateMock).toHaveBeenCalledWith({ default_model: "gpt-4o" });
  });
});
