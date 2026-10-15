import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SettingsView from "../routes/SettingsView";
import { ApiError } from "../lib/api";
import { COPY } from "../routes/setup/copy";

const { useSettingsMock, mutateAsyncMock, fetchModelsMock } = vi.hoisted(() => ({
  useSettingsMock: vi.fn(),
  mutateAsyncMock: vi.fn(),
  fetchModelsMock: vi.fn(),
}));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => useSettingsMock(),
  useUpdateSettings: () => ({
    mutate: vi.fn(),
    mutateAsync: mutateAsyncMock,
    isPending: false,
    isSuccess: false,
    isError: false,
  }),
}));

vi.mock("../routes/setup/useFetchModels", () => ({
  useFetchModels: () => ({
    models: [],
    isLoading: false,
    error: null,
    fetchModels: fetchModelsMock,
  }),
}));

describe("SettingsView", () => {
  beforeEach(() => {
    useSettingsMock.mockReset();
    mutateAsyncMock.mockReset();
    fetchModelsMock.mockReset();
    // The PUT echoes the persisted settings, including the submitted provider.
    mutateAsyncMock.mockImplementation(
      (data: { provider_type?: string | null; base_url?: string | null; default_model?: string }) =>
        Promise.resolve({
          user_id: 1,
          has_api_key: false,
          provider_type: data.provider_type ?? null,
          base_url: data.base_url ?? null,
          default_model: data.default_model ?? null,
          allowed_models: [],
        }),
    );
    // Default probe succeeds; individual tests override it.
    fetchModelsMock.mockResolvedValue({ models: [], error: null });
  });

  it("renders the form without an infinite render loop", () => {
    // Regression: reset() used to run during render, looping forever
    // (blank screen). If the loop returns, this test times out.
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini"],
      },
      isLoading: false,
    });
    render(<SettingsView />);
    expect(screen.getByText("Ajustes")).toBeTruthy();
    expect(screen.getByPlaceholderText("sk-...")).toBeTruthy();
    // Model picker is a dropdown fed by the server whitelist
    const select = screen.getByLabelText("Modelo predeterminado") as HTMLSelectElement;
    expect(select.options.length).toBe(6); // "" + 5 allowed models
    // Provider picker is a dropdown fed by the shared preset catalog
    const providerSelect = screen.getByLabelText("Proveedor") as HTMLSelectElement;
    expect(providerSelect.options.length).toBe(6); // "" + 5 presets
  });

  it("shows the selected model in the dropdown", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: true,
        default_model: "gpt-4o",
        allowed_models: ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini"],
      },
      isLoading: false,
    });
    render(<SettingsView />);
    expect(screen.getByText(/guardada — deja en blanco para mantenerla/i)).toBeTruthy();
    const keyInput = screen.getByPlaceholderText("sk-...") as HTMLInputElement;
    expect(keyInput.value).toBe("");
    const select = screen.getByLabelText("Modelo predeterminado") as HTMLSelectElement;
    expect(select.value).toBe("gpt-4o");
  });

  it("prefills provider and base_url from saved settings", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: true,
        default_model: null,
        allowed_models: [],
        provider_type: "openrouter",
        base_url: "https://openrouter.ai/api/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);
    const providerSelect = screen.getByLabelText("Proveedor") as HTMLSelectElement;
    expect(providerSelect.value).toBe("openrouter");
    const baseUrlInput = screen.getByLabelText("URL base") as HTMLInputElement;
    expect(baseUrlInput.value).toBe("https://openrouter.ai/api/v1");
  });

  it("submits provider_type, base_url and api_key", async () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
      },
      isLoading: false,
    });
    render(<SettingsView />);

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("URL base"), {
      target: { value: "https://api.example.com/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText("sk-..."), {
      target: { value: "sk-new" },
    });
    fireEvent.click(screen.getByRole("button", { name: /guardar/i }));

    await waitFor(() => expect(mutateAsyncMock).toHaveBeenCalledTimes(1));
    expect(mutateAsyncMock).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "custom",
        base_url: "https://api.example.com/v1",
        api_key: "sk-new",
      }),
    );
  });

  it("resets base_url to the preset default when the provider changes", async () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
      },
      isLoading: false,
    });
    render(<SettingsView />);

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "ollama" } });

    const baseUrlInput = screen.getByLabelText("URL base") as HTMLInputElement;
    await waitFor(() => expect(baseUrlInput.value).toBe("http://localhost:11434/v1"));
  });

  it("shows the loading state", () => {
    useSettingsMock.mockReturnValue({ data: undefined, isLoading: true });
    render(<SettingsView />);
    expect(screen.getByText(/cargando ajustes/i)).toBeTruthy();
  });

  it("shows error card when useSettings fails (R-ErrorUI-4)", () => {
    useSettingsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load settings"),
      refetch: vi.fn(),
    });
    render(<SettingsView />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("locks base_url for a named preset and unlocks with Edit URL", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "openrouter",
        base_url: "https://openrouter.ai/api/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    const baseUrlInput = screen.getByLabelText("URL base") as HTMLInputElement;
    expect(baseUrlInput.readOnly).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /editar url/i }));
    expect(baseUrlInput.readOnly).toBe(false);
  });

  it("preserves a saved custom base_url for a named preset (gateway)", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "openrouter",
        base_url: "https://gateway.internal/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    const baseUrlInput = screen.getByLabelText("URL base") as HTMLInputElement;
    expect(baseUrlInput.value).toBe("https://gateway.internal/v1");
    expect(baseUrlInput.readOnly).toBe(true);
    expect(screen.getByText(/url personalizada/i)).toBeTruthy();
  });

  it("leaves base_url editable for custom without a toggle", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "custom",
        base_url: "https://api.example.com/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    const baseUrlInput = screen.getByLabelText("URL base") as HTMLInputElement;
    expect(baseUrlInput.readOnly).toBe(false);
    expect(screen.queryByRole("button", { name: /editar url/i })).toBeNull();
  });

  it("Use default restores the preset default while staying in edit mode", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "openrouter",
        base_url: "https://gateway.internal/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    const baseUrlInput = screen.getByLabelText("URL base") as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: /editar url/i }));
    fireEvent.click(screen.getByRole("button", { name: /usar predeterminada/i }));

    expect(baseUrlInput.value).toBe("https://openrouter.ai/api/v1");
    expect(baseUrlInput.readOnly).toBe(false);
  });

  it("Lock keeps an edited custom URL and re-locks the field", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "openrouter",
        base_url: "https://gateway.internal/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    const baseUrlInput = screen.getByLabelText("URL base") as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: /editar url/i }));
    fireEvent.change(baseUrlInput, { target: { value: "https://my-gateway.example/v1" } });
    fireEvent.click(screen.getByRole("button", { name: /^bloquear$/i }));

    expect(baseUrlInput.value).toBe("https://my-gateway.example/v1");
    expect(baseUrlInput.readOnly).toBe(true);
    expect(screen.getByText(/url personalizada/i)).toBeTruthy();
  });

  it("reports a failed probe honestly after a successful save", async () => {
    useSettingsMock.mockReturnValue({
      data: { user_id: 1, has_api_key: false, default_model: null, allowed_models: [] },
      isLoading: false,
    });
    fetchModelsMock.mockResolvedValue({
      models: [],
      error: { code: "provider_error", message: "401 Unauthorized" },
    });
    render(<SettingsView />);

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("URL base"), {
      target: { value: "https://api.example.com/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /guardar/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/guardado, pero falló la conexión: 401 unauthorized/i),
      ).toBeTruthy(),
    );
    expect(fetchModelsMock).toHaveBeenCalledTimes(1);
    // The unverified save must NOT masquerade as a plain success.
    expect(screen.queryByText(/^Ajustes guardados$/)).toBeNull();
    expect(screen.getByRole("alert").textContent).toMatch(/falló la conexión/i);
  });

  it("shows connected when the probe succeeds", async () => {
    useSettingsMock.mockReturnValue({
      data: { user_id: 1, has_api_key: false, default_model: null, allowed_models: [] },
      isLoading: false,
    });
    fetchModelsMock.mockResolvedValue({
      models: [{ id: "gpt-4o", name: "gpt-4o" }],
      error: null,
    });
    render(<SettingsView />);

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("URL base"), {
      target: { value: "https://api.example.com/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /guardar/i }));

    await waitFor(() => expect(screen.getByText(/guardado · conectado/i)).toBeTruthy());
    expect(fetchModelsMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the save error and does not probe when the PUT fails", async () => {
    useSettingsMock.mockReturnValue({
      data: { user_id: 1, has_api_key: false, default_model: null, allowed_models: [] },
      isLoading: false,
    });
    mutateAsyncMock.mockRejectedValue(new Error("boom"));
    render(<SettingsView />);

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("URL base"), {
      target: { value: "https://api.example.com/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /guardar/i }));

    await waitFor(() =>
      expect(screen.getByText(/no se pudieron guardar los ajustes: boom/i)).toBeTruthy(),
    );
    expect(fetchModelsMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("shows the friendly SSRF copy when the base_url is rejected", async () => {
    // The API answers a rejected base_url with 422 and a {code,message}
    // detail object (server/api/routers/settings.py, BaseUrlRejected). The
    // wizard maps that code to Spanish copy; the hub must too, instead of
    // leaking the raw "API error 422".
    useSettingsMock.mockReturnValue({
      data: { user_id: 1, has_api_key: false, default_model: null, allowed_models: [] },
      isLoading: false,
    });
    mutateAsyncMock.mockRejectedValue(
      new ApiError(422, {
        detail: {
          code: "invalid_base_url",
          message: "base_url must point to a public host",
        },
      }),
    );
    render(<SettingsView />);

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("URL base"), {
      target: { value: "http://localhost:1234/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /guardar/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    const alert = screen.getByRole("alert").textContent ?? "";
    expect(alert).toContain(COPY.SSRF_REJECTION);
    expect(alert).not.toMatch(/API error 422/);
    expect(fetchModelsMock).not.toHaveBeenCalled();
  });

  it("shows plain success without probing when the provider is cleared", async () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: true,
        default_model: null,
        allowed_models: [],
        provider_type: "openrouter",
        base_url: "https://openrouter.ai/api/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /guardar/i }));

    await waitFor(() => expect(screen.getByText(/^Ajustes guardados$/)).toBeTruthy());
    expect(fetchModelsMock).not.toHaveBeenCalled();
  });

  it("renders paid and free recommended models with prices and the recommended marker", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "openrouter",
        base_url: "https://openrouter.ai/api/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    // Paid option with input/output token prices (two paid models share $2/$10).
    expect(screen.getByText("Claude Sonnet 5.5")).toBeTruthy();
    expect(
      screen.getAllByText("Entrada $2.00 / Salida $10.00 por 1M tokens").length,
    ).toBeGreaterThan(0);
    // Free option.
    expect(screen.getByText("Ling 3.1 Flash")).toBeTruthy();
    // Tier badges and the recommended marker are present.
    expect(screen.getAllByText("De pago").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Gratis").length).toBeGreaterThan(0);
    expect(screen.getAllByText("(Recomendado)").length).toBeGreaterThan(0);
  });

  it("renders the OpenRouter guide with a setup link that opens in a new tab", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "openrouter",
        base_url: "https://openrouter.ai/api/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    expect(screen.getByText(/cómo configurar openrouter/i)).toBeTruthy();
    const sectionLink = screen.getByRole("link", {
      name: /obtener una clave de api en openrouter/i,
    });
    expect(sectionLink.getAttribute("href")).toBe("https://openrouter.ai/keys");
    expect(sectionLink.getAttribute("target")).toBe("_blank");
    expect(sectionLink.getAttribute("rel")).toBe("noopener noreferrer");

    const guideLink = screen.getByRole("link", { name: /abrir openrouter/i });
    expect(guideLink.getAttribute("target")).toBe("_blank");
  });

  it("keys the catalog and guide to the selected provider (Groq)", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "groq",
        base_url: "https://api.groq.com/openai/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    // Groq catalog, no OpenRouter entries and no free tier group.
    expect(screen.getByText("GPT-OSS 120B")).toBeTruthy();
    expect(screen.getByText("Qwen 3.8 27B (preview)")).toBeTruthy();
    expect(screen.getByText("Entrada $0.15 / Salida $0.60 por 1M tokens")).toBeTruthy();
    expect(screen.queryByText("Claude Sonnet 5.5")).toBeNull();
    expect(screen.queryByText("Gratis")).toBeNull();

    // Groq guide and provider-appropriate setup link, not OpenRouter's.
    expect(screen.getByText(/cómo configurar groq/i)).toBeTruthy();
    const sectionLink = screen.getByRole("link", {
      name: /obtener una clave de api en groq/i,
    });
    expect(sectionLink.getAttribute("href")).toBe("https://console.groq.com/keys");
  });

  it("hides the catalog when the provider has none and still shows its guide (Ollama)", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: "llama3.2:latest",
        allowed_models: [],
        provider_type: "ollama",
        base_url: "http://localhost:11434/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    expect(screen.queryByText("Modelos recomendados")).toBeNull();
    expect(screen.getByText(/cómo configurar ollama/i)).toBeTruthy();
  });

  it("renders a free-text model input for an unrestricted provider (D6)", () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: "llama3.2:latest",
        allowed_models: ["gpt-4o"],
        provider_type: "ollama",
        base_url: "http://localhost:11434/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    // No whitelist dropdown; a text input bound to default_model instead.
    expect(screen.queryByRole("combobox", { name: "Modelo predeterminado" })).toBeNull();
    const modelInput = screen.getByLabelText("Modelo predeterminado") as HTMLInputElement;
    expect(modelInput.tagName).toBe("INPUT");
    expect(modelInput.value).toBe("llama3.2:latest");
  });

  it("submits a free-text model for an unrestricted provider", async () => {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "ollama",
        base_url: "http://localhost:11434/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);

    fireEvent.change(screen.getByLabelText("Modelo predeterminado"), {
      target: { value: "mi-modelo-local" },
    });
    fireEvent.click(screen.getByRole("button", { name: /guardar/i }));

    await waitFor(() =>
      expect(mutateAsyncMock).toHaveBeenCalledWith(
        expect.objectContaining({
          default_model: "mi-modelo-local",
          provider_type: "ollama",
        }),
      ),
    );
  });

  function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((r) => {
      resolve = r;
    });
    return { promise, resolve };
  }

  function renderOpenRouterForm() {
    useSettingsMock.mockReturnValue({
      data: {
        user_id: 1,
        has_api_key: false,
        default_model: null,
        allowed_models: [],
        provider_type: "openrouter",
        base_url: "https://openrouter.ai/api/v1",
      },
      isLoading: false,
    });
    render(<SettingsView />);
  }

  it("reports a probe rejection as saved-unverified after a successful save (R3-001)", async () => {
    renderOpenRouterForm();
    fetchModelsMock.mockRejectedValue(new Error("network down"));

    fireEvent.click(screen.getByRole("button", { name: /guardar/i }));

    await waitFor(() =>
      expect(screen.getByText(/guardado, pero falló la conexión: network down/i)).toBeTruthy(),
    );
    expect(screen.getByRole("alert").textContent).toMatch(/falló la conexión/i);
  });

  it("falls back to the submitted provider when the PUT response omits provider_type (R3-003)", async () => {
    useSettingsMock.mockReturnValue({
      data: { user_id: 1, has_api_key: false, default_model: null, allowed_models: [] },
      isLoading: false,
    });
    render(<SettingsView />);
    mutateAsyncMock.mockResolvedValue({
      user_id: 1,
      has_api_key: false,
      provider_type: undefined,
      base_url: "https://api.example.com/v1",
      default_model: null,
      allowed_models: [],
    });

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("URL base"), {
      target: { value: "https://api.example.com/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /guardar/i }));

    await waitFor(() => expect(screen.getByText(/guardado · conectado/i)).toBeTruthy());
    expect(fetchModelsMock).toHaveBeenCalledTimes(1);
  });

  it("shows in-flight button states during save and probe, then connected (R3-004, WU4-R3-001)", async () => {
    renderOpenRouterForm();
    const savedSettings = {
      user_id: 1,
      has_api_key: false,
      provider_type: "openrouter" as const,
      base_url: "https://openrouter.ai/api/v1",
      default_model: null,
      allowed_models: [] as string[],
    };
    const putGate = deferred<typeof savedSettings>();
    const probeGate = deferred<{ models: { id: string; name: string }[]; error: null }>();
    mutateAsyncMock.mockReturnValue(putGate.promise);
    fetchModelsMock.mockReturnValue(probeGate.promise);

    fireEvent.click(screen.getByRole("button", { name: /^guardar$/i }));

    const saving = (await waitFor(() =>
      screen.getByRole("button", { name: "Guardando..." }),
    )) as HTMLButtonElement;
    expect(saving.disabled).toBe(true);

    putGate.resolve(savedSettings);
    await waitFor(() => expect(screen.getByRole("button", { name: "Comprobando..." })).toBeTruthy());
    const checking = screen.getByRole("button", { name: "Comprobando..." }) as HTMLButtonElement;
    expect(checking.disabled).toBe(true);

    // Unasserted literals from the WU4 changed-literals sweep.
    expect(
      screen.getByText("Predeterminado del servidor (variable OPENAI_MODEL)"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Se guarda en el servidor y nunca se devuelve al navegador\. Si se deja vacía, se usa la variable de entorno OPENAI_API_KEY\./,
      ),
    ).toBeTruthy();

    probeGate.resolve({ models: [], error: null });
    await waitFor(() => expect(screen.getByText(/guardado · conectado/i)).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Comprobando..." })).toBeNull();
  });
});
