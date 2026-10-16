import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import SettingsView from "../routes/SettingsView";
import { renderWithProviders } from "./test-utils";
import { COPY } from "../routes/setup/copy";
import { RECOMMENDED_MODELS } from "../routes/settings/recommended";

const { useSettingsMock, mutateAsyncMock, fetchModelsMock, useFetchModelsMock } = vi.hoisted(
  () => ({
    useSettingsMock: vi.fn(),
    mutateAsyncMock: vi.fn(),
    fetchModelsMock: vi.fn(),
    useFetchModelsMock: vi.fn(),
  })
);

vi.mock("../queries/useSettings", () => ({
  useSettings: () => useSettingsMock(),
  useUpdateSettings: () => ({ mutateAsync: mutateAsyncMock, isPending: false }),
}));

vi.mock("../routes/setup/useFetchModels", () => ({
  useFetchModels: () => useFetchModelsMock(),
}));

const emptySettings = {
  user_id: 1,
  has_api_key: false,
  default_model: null,
  allowed_models: ["gpt-4o", "gpt-4o-mini", ...RECOMMENDED_MODELS.map((m) => m.model)],
  provider_type: null,
  base_url: null,
};

function setupMocks(settingsOverrides: Record<string, unknown> = {}) {
  useSettingsMock.mockReset();
  mutateAsyncMock.mockReset();
  fetchModelsMock.mockReset();
  useFetchModelsMock.mockReset();

  useSettingsMock.mockReturnValue({
    data: { ...emptySettings, ...settingsOverrides },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
  // The PUT echoes what was persisted, including the provider.
  mutateAsyncMock.mockImplementation((data: Record<string, unknown>) =>
    Promise.resolve({
      ...emptySettings,
      ...settingsOverrides,
      provider_type: data.provider_type ?? null,
      base_url: data.base_url ?? null,
      default_model: data.default_model ?? null,
    })
  );
  fetchModelsMock.mockResolvedValue({ models: [], error: null });
  useFetchModelsMock.mockReturnValue({
    models: [],
    isLoading: false,
    error: null,
    fetchModels: fetchModelsMock,
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

/**
 * The full view, reached through the mode switch when the guided flow is what
 * opens by default (an unconfigured app).
 */
function renderHub(overrides: Record<string, unknown> = {}) {
  setupMocks(overrides);
  const utils = renderWithProviders(<SettingsView />, { route: "/app/settings" });
  if (screen.queryAllByRole("radio").length > 0) {
    fireEvent.click(screen.getByRole("button", { name: "Avanzado" }));
  }
  return utils;
}

beforeEach(() => {
  // The chosen arrangement is remembered per origin, so it would otherwise leak
  // from one test to the next (each test is a fresh "browser session").
  window.localStorage.clear();
  setupMocks();
});

describe("SettingsView — la vista completa (Avanzado)", () => {
  it("renders the fields without an infinite render loop", () => {
    // Regression: reset() used to run during render, looping forever (blank
    // screen). If the loop returns, this test times out.
    renderHub();
    expect(screen.getByText("Ajustes")).toBeTruthy();
    expect(screen.getByLabelText("Proveedor")).toBeTruthy();
    expect(screen.getByLabelText("URL base")).toBeTruthy();
  });

  it("prefills the saved provider and its saved url (gateway override kept)", () => {
    renderHub({
      provider_type: "openrouter",
      base_url: "https://gateway.example.com/v1",
      default_model: "gpt-4o",
      has_api_key: true,
    });

    expect((screen.getByLabelText("Proveedor") as HTMLSelectElement).value).toBe(
      "openrouter"
    );
    expect((screen.getByLabelText("URL base") as HTMLInputElement).value).toBe(
      "https://gateway.example.com/v1"
    );
    expect(screen.getByText(/URL personalizada/)).toBeTruthy();
    expect((screen.getByLabelText("Modelo predeterminado") as HTMLSelectElement).value).toBe(
      "gpt-4o"
    );
  });

  it("fills the preset default url when nothing was saved and locks it", () => {
    renderHub({ provider_type: "openrouter", base_url: null });

    const url = screen.getByLabelText("URL base") as HTMLInputElement;
    expect(url.value).toBe("https://openrouter.ai/api/v1");
    expect(url.readOnly).toBe(true);
    expect(screen.getByText("URL predeterminada del proveedor.")).toBeTruthy();
  });

  it("unlocks the url to edit it, and locks it again", () => {
    renderHub({ provider_type: "openrouter", base_url: null });

    fireEvent.click(screen.getByText("Editar URL"));
    const url = screen.getByLabelText("URL base") as HTMLInputElement;
    expect(url.readOnly).toBe(false);

    fireEvent.click(screen.getByText("Bloquear"));
    expect((screen.getByLabelText("URL base") as HTMLInputElement).readOnly).toBe(true);
  });

  it("restores the preset default while staying in edit mode", () => {
    renderHub({ provider_type: "openrouter", base_url: "https://gateway.example.com/v1" });

    fireEvent.click(screen.getByText("Editar URL"));
    fireEvent.change(screen.getByLabelText("URL base"), {
      target: { value: "https://otro.example.com/v1" },
    });
    fireEvent.click(screen.getByText("Usar predeterminada"));

    expect((screen.getByLabelText("URL base") as HTMLInputElement).value).toBe(
      "https://openrouter.ai/api/v1"
    );
    expect((screen.getByLabelText("URL base") as HTMLInputElement).readOnly).toBe(false);
  });

  it("leaves the url editable for a custom provider, with no toggle", () => {
    renderHub({ provider_type: "custom", base_url: "https://mio.example.com/v1" });

    expect((screen.getByLabelText("URL base") as HTMLInputElement).readOnly).toBe(false);
    expect(screen.queryByText("Editar URL")).toBeNull();
  });

  it("resets base_url to the new preset default when the provider changes", () => {
    renderHub({ provider_type: "openrouter", base_url: "https://gateway.example.com/v1" });

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "ollama" } });

    expect((screen.getByLabelText("URL base") as HTMLInputElement).value).toBe(
      "http://localhost:11434/v1"
    );
  });

  it("saves everything in one call and reports the probe honestly", async () => {
    renderHub({ provider_type: "openrouter", has_api_key: true });

    fireEvent.change(screen.getByLabelText(/Clave de API/), {
      target: { value: "sk-new" },
    });
    fireEvent.change(screen.getByLabelText("Modelo predeterminado"), {
      target: { value: "gpt-4o" },
    });
    fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.SAVE }));

    await waitFor(() =>
      expect(mutateAsyncMock).toHaveBeenCalledWith({
        provider_type: "openrouter",
        base_url: "https://openrouter.ai/api/v1",
        api_key: "sk-new",
        default_model: "gpt-4o",
      })
    );
    expect(fetchModelsMock).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByText(COPY.STATUS.CONNECTED)).toBeTruthy());
  });

  it("reports a failed probe instead of pretending success", async () => {
    renderHub({ provider_type: "openrouter", has_api_key: true });
    fetchModelsMock.mockResolvedValue({
      models: [],
      error: { code: "timeout", message: "sin respuesta" },
    });

    fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.SAVE }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(
        COPY.STATUS.UNVERIFIED("sin respuesta")
      )
    );
  });

  it("shows the friendly SSRF copy and never probes when the PUT fails", async () => {
    renderHub({ provider_type: "custom", base_url: "https://mio.example.com/v1", has_api_key: true });
    mutateAsyncMock.mockRejectedValue({
      body: { detail: { code: "invalid_base_url", message: "blocked" } },
    });

    fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.SAVE }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(
        COPY.STATUS.SAVE_ERROR(COPY.SSRF_REJECTION)
      )
    );
    expect(fetchModelsMock).not.toHaveBeenCalled();
  });

  it("reports a plain success without probing when the provider is cleared", async () => {
    renderHub({ provider_type: "openrouter", has_api_key: true });
    mutateAsyncMock.mockResolvedValue({ ...emptySettings, provider_type: null });

    fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.SAVE }));

    await waitFor(() => expect(screen.getByText(COPY.STATUS.SAVED)).toBeTruthy());
    expect(fetchModelsMock).not.toHaveBeenCalled();
  });

  it("falls back to the submitted provider when the PUT omits it", async () => {
    renderHub({ provider_type: "openrouter", has_api_key: true });
    mutateAsyncMock.mockResolvedValue({ ...emptySettings, provider_type: undefined });

    fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.SAVE }));

    await waitFor(() => expect(fetchModelsMock).toHaveBeenCalledTimes(1));
  });

  it("shows both in-flight states, then the connected result", async () => {
    renderHub({ provider_type: "openrouter", has_api_key: true });
    const saving = deferred<unknown>();
    const probing = deferred<unknown>();
    mutateAsyncMock.mockReturnValue(saving.promise);
    fetchModelsMock.mockReturnValue(probing.promise);

    fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.SAVE }));
    expect(screen.getByText(COPY.STATUS.SAVING)).toBeTruthy();

    saving.resolve({ ...emptySettings, provider_type: "openrouter" });
    await waitFor(() => expect(screen.getByText(COPY.STATUS.CHECKING)).toBeTruthy());

    probing.resolve({ models: [], error: null });
    await waitFor(() => expect(screen.getByText(COPY.STATUS.CONNECTED)).toBeTruthy());
  });

  it("renders the curated catalog with prices and lets a card set the model", () => {
    renderHub({ provider_type: "openrouter", has_api_key: true });

    expect(screen.getByRole("heading", { name: "De pago" })).toBeTruthy();
    // "Gratis" is both the tier heading and the price tag of every free model.
    expect(screen.getByRole("heading", { name: "Gratis" })).toBeTruthy();
    // Two catalog models share this price, so assert it inside the card.
    const card = screen.getByRole("button", { name: /Claude Sonnet 5\.5/ });
    expect(card.textContent).toContain("Entrada $2.00 / Salida $10.00 por 1M tokens");
    expect(card.textContent).toContain("(Recomendado)");

    fireEvent.click(card);

    expect((screen.getByLabelText("Modelo predeterminado") as HTMLSelectElement).value).toBe(
      "anthropic/claude-sonnet-5.5"
    );
  });

  it("keys the catalog and the guide to the selected provider", () => {
    renderHub({ provider_type: "groq", has_api_key: true });

    expect(screen.getByText(/GPT-OSS 120B/)).toBeTruthy();
    expect(screen.getByText("Cómo configurar Groq")).toBeTruthy();
    expect(screen.queryByText("Cómo configurar OpenRouter")).toBeNull();
  });

  it("opens the guide link in a new tab without leaking the opener", () => {
    renderHub({ provider_type: "openrouter", has_api_key: true });

    const link = screen.getByText("Abrir OpenRouter") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("https://openrouter.ai/keys");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("hides the catalog for a provider without one but still shows its guide", () => {
    renderHub({ provider_type: "ollama" });

    expect(screen.queryByText("Modelos recomendados")).toBeNull();
    expect(screen.getByText("Cómo configurar Ollama")).toBeTruthy();
    // Keyless provider: no key field, and the endpoint is stated instead.
    expect(screen.queryByLabelText(/Clave de API/)).toBeNull();
    expect(screen.getByText("Endpoint que usará Datara:")).toBeTruthy();
  });

  it("uses the whitelist dropdown for a restricted provider and free text for the others", () => {
    renderHub({ provider_type: "openrouter", has_api_key: true });
    const select = screen.getByLabelText("Modelo predeterminado") as HTMLSelectElement;
    expect(select.tagName).toBe("SELECT");
    // The catalog labels make the whitelist readable; unknown ids stay raw.
    const options = Array.from(select.options).map((option) => option.textContent);
    expect(options).toContain("Claude Sonnet 5.5");
    expect(options).toContain("gpt-4o");
    expect(select.value).toBe("");
  });

  it("offers free-text model entry for an unrestricted provider (D6)", () => {
    renderHub({ provider_type: "groq", has_api_key: true });
    const model = screen.getByLabelText("Modelo predeterminado") as HTMLInputElement;
    expect(model.tagName).toBe("INPUT");
    expect(model.placeholder).toBe("openai/gpt-oss-120b");
  });

  it("shows the loading state and the error card", () => {
    useSettingsMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });
    const { unmount } = renderWithProviders(<SettingsView />, {
      route: "/app/settings?variante=b",
    });
    expect(screen.getByText("Cargando ajustes...")).toBeTruthy();
    unmount();

    useSettingsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("boom"),
      refetch: vi.fn(),
    });
    renderWithProviders(<SettingsView />, { route: "/app/settings?variante=b" });
    expect(screen.getByText("Something went wrong")).toBeTruthy();
  });
});

describe("SettingsView — el modo no se cambia solo", () => {
  it("keeps the guided flow when saving the provider makes the app configured (O10)", async () => {
    // Reproduces what the usability round found: the provider had been cleared
    // but a model was still stored, so the app opened in the guided flow.
    // Saving the provider flipped "is it configured?" to true, and because the
    // mode was re-derived on every render, the screen jumped to the full view
    // and cut the step-by-step in half.
    const live: Record<string, unknown> = {
      ...emptySettings,
      provider_type: null,
      default_model: "gpt-4o",
      has_api_key: false,
    };
    useSettingsMock.mockImplementation(() => ({
      data: live,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    }));
    // The PUT updates the stored row; the settings query would refetch it.
    mutateAsyncMock.mockImplementation(async (data: Record<string, unknown>) => {
      Object.assign(live, data);
      return { ...live };
    });
    fetchModelsMock.mockResolvedValue({ models: [], error: null });

    renderWithProviders(<SettingsView />, { route: "/app/settings" });

    // Unconfigured: the guided flow is open (provider radios, not a dropdown).
    fireEvent.click(screen.getByRole("radio", { name: /OpenRouter/ }));
    fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.NEXT }));
    fireEvent.change(await screen.findByPlaceholderText("sk-..."), {
      target: { value: "sk-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.NEXT }));

    // Still guided after the save: the step indicator is the discriminator, the
    // full view has no steps at all.
    expect(await screen.findByText(COPY.GUIDED_STEPS[3])).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
  });
});

describe("SettingsView — los dos modos (la forma elegida)", () => {
  it("opens the guided flow when nothing is configured, and switches to the full view", () => {
    setupMocks();
    renderWithProviders(<SettingsView />, { route: "/app/settings" });

    // Unconfigured: guided by default (S5), so the provider radios are shown.
    expect(screen.getByRole("radio", { name: /OpenRouter/ })).toBeTruthy();
    expect(screen.queryByLabelText("URL base")).toBeNull();

    fireEvent.click(screen.getByText("Avanzado"));
    expect(screen.getByLabelText("URL base")).toBeTruthy();
  });

  it("returns from the guided flow to the full view", () => {
    setupMocks();
    renderWithProviders(<SettingsView />, { route: "/app/settings" });

    expect(screen.getByRole("radio", { name: /OpenRouter/ })).toBeTruthy();
    fireEvent.click(screen.getByText("Volver a la vista completa"));
    expect(screen.getByLabelText("URL base")).toBeTruthy();
  });

  it("opens the full view when the app is already configured, with the way back offered", () => {
    setupMocks({ provider_type: "openrouter", default_model: "gpt-4o", has_api_key: true });
    renderWithProviders(<SettingsView />, { route: "/app/settings" });

    expect(screen.getByLabelText("URL base")).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
    // The switch stays available: the guided flow is never a one-way door.
    expect(screen.getByRole("button", { name: "Guiado" })).toBeTruthy();
  });

  it("never links to a second settings screen", () => {
    // The arrangement that won puts everything in one screen; the other two and
    // their link to /app/setup were deleted with the scaffolding.
    setupMocks();
    renderWithProviders(<SettingsView />, { route: "/app/settings" });

    expect(screen.queryByText("Configurar paso a paso")).toBeNull();
  });

  it("ignores a stale ?variante= left in a bookmark", () => {
    setupMocks();
    renderWithProviders(<SettingsView />, { route: "/app/settings?variante=c" });

    // Nothing reads that parameter any more: an old bookmark cannot resurrect a
    // deleted arrangement.
    expect(screen.getByRole("radio", { name: /OpenRouter/ })).toBeTruthy();
    expect(screen.queryByText("Configurar paso a paso")).toBeNull();
  });
});
