import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import Setup from "../routes/Setup";
import { renderWithProviders } from "./test-utils";
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
  useUpdateSettings: () => ({
    mutateAsync: mutateMock,
    mutate: mutateMock,
    isPending: false,
  }),
}));

vi.mock("../routes/setup/useFetchModels", () => ({
  useFetchModels: () => useFetchModelsMock(),
}));

const emptySettings = {
  user_id: 1,
  has_api_key: false,
  default_model: null,
  // Mirrors the shipped whitelist: base models + the curated catalog.
  allowed_models: [
    "gpt-4o",
    "gpt-4o-mini",
    ...RECOMMENDED_MODELS.map((m) => m.model),
  ],
  provider_type: null,
  base_url: null,
};

interface LiveModel {
  id: string;
  name: string;
}
interface ProbeError {
  code: string;
  message: string;
}

function setupMocks(
  settingsOverrides: Record<string, unknown> = {},
  models: LiveModel[] = [],
  fetchError: ProbeError | null = null
) {
  useSettingsMock.mockReset();
  mutateMock.mockReset();
  fetchModelsMock.mockReset();
  useFetchModelsMock.mockReset();

  useSettingsMock.mockReturnValue({
    data: { ...emptySettings, ...settingsOverrides },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
  mutateMock.mockResolvedValue(undefined);
  fetchModelsMock.mockResolvedValue({ models, error: fetchError });
  useFetchModelsMock.mockReturnValue({
    models,
    isLoading: false,
    error: fetchError ? new Error(fetchError.message) : null,
    fetchModels: fetchModelsMock,
  });
}

const OPENROUTER = "OpenRouter (clave de API requerida)";
const GROQ = "Groq (clave de API requerida)";
const OLLAMA = "Ollama";
const LMSTUDIO = "LM Studio";
const CUSTOM = "Custom (clave de API requerida)";

function renderSetup() {
  return renderWithProviders(<Setup />, { route: "/app/setup" });
}

function choose(name: string | RegExp) {
  fireEvent.click(screen.getByRole("radio", { name }));
}

function next() {
  fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.NEXT }));
}

/**
 * Advance the model step by clicking Finalizar (save the model, then probe).
 *
 * This is the real user path. It used to dispatch the form's submit event
 * instead, because the button was stuck disabled by the lifecycle bug now
 * guarded at the end of this file.
 */
function finish() {
  fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.FINISH }));
}

function previous() {
  fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.PREVIOUS }));
}

async function enterKey(value = "sk-test") {
  const input = await screen.findByPlaceholderText("sk-...");
  fireEvent.change(input, { target: { value } });
  return input as HTMLInputElement;
}

beforeEach(() => {
  setupMocks();
});

describe("Setup — guided flow", () => {
  it("shows the four guided steps and never the old five", () => {
    renderSetup();

    expect(COPY.GUIDED_STEPS).toHaveLength(4);
    for (const label of COPY.GUIDED_STEPS) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    // The connection test and the confirmation stopped being steps by design.
    expect(screen.queryByText("Prueba de conexión")).toBeNull();
    expect(screen.queryByText("Listo")).toBeNull();
  });

  it("offers the five presets as selectable radios and requires a choice", async () => {
    renderSetup();

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios).toHaveLength(5);
    expect(radios.every((radio) => !radio.disabled)).toBe(true);
    for (const name of [OPENROUTER, OLLAMA, LMSTUDIO, GROQ, CUSTOM]) {
      expect(screen.getByRole("radio", { name })).toBeTruthy();
    }

    next();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe(COPY.PROVIDER_REQUIRED);
    // Still on the provider step.
    expect(screen.getByRole("radio", { name: OLLAMA })).toBeTruthy();
  });

  it("offers a stored provider that no preset carries and lets it continue", async () => {
    setupMocks({
      provider_type: "mistral",
      base_url: "https://api.mistral.ai/v1",
      has_api_key: true,
    });
    renderSetup();

    const legacy = screen.getByRole("radio", {
      name: /Otro \(mistral\)/,
    }) as HTMLInputElement;
    expect(legacy.checked).toBe(true);

    choose(/Otro \(mistral\)/);
    next();

    expect(await screen.findByPlaceholderText("sk-...")).toBeTruthy();
    expect(screen.getByText(/guardada/)).toBeTruthy();
  });

  it("shows the endpoint note and no key field for a keyless provider, and advances", async () => {
    renderSetup();

    choose(OLLAMA);
    next();

    expect(await screen.findByText(COPY.KEYLESS_NO_KEY_REQUIRED("Ollama"))).toBeTruthy();
    expect(screen.getByText(/Endpoint que usará Datara:/)).toBeTruthy();
    expect(screen.getByText("http://localhost:11434/v1")).toBeTruthy();
    expect(screen.getByText(COPY.KEYLESS_SERVER_HINT("Ollama"))).toBeTruthy();
    // Read-only: no key field for a keyless provider.
    expect(screen.queryByPlaceholderText("sk-...")).toBeNull();

    next();

    expect(await screen.findByText("Modelo predeterminado")).toBeTruthy();
  });

  it("validates the key, accepts a stored key, and requires the custom base url", async () => {
    // Empty key with no stored key: blocked.
    const a = renderSetup();
    choose(OPENROUTER);
    next();
    await screen.findByPlaceholderText("sk-...");
    next();
    expect(await screen.findByText(COPY.KEY_REQUIRED)).toBeTruthy();
    expect(screen.getByPlaceholderText("sk-...")).toBeTruthy();
    a.unmount();

    // A stored key advances without retyping.
    setupMocks({ provider_type: "openrouter", has_api_key: true });
    const b = renderSetup();
    expect(
      (screen.getByRole("radio", { name: OPENROUTER }) as HTMLInputElement).checked
    ).toBe(true);
    next();
    await screen.findByPlaceholderText("sk-...");
    next();
    expect(await screen.findByText("Modelo predeterminado")).toBeTruthy();
    b.unmount();

    // Custom without a base url: blocked even with a key typed.
    setupMocks();
    const c = renderSetup();
    choose(CUSTOM);
    next();
    await enterKey("sk-x");
    next();
    expect(await screen.findByText(COPY.BASE_URL_REQUIRED)).toBeTruthy();
    expect(screen.getByText("URL base")).toBeTruthy();
    c.unmount();
  });

  it("persists credentials in one PUT, keeps a rejected save on the step, and never renders the key", async () => {
    const a = renderSetup();
    choose(OPENROUTER);
    next();
    await enterKey("sk-secret");
    next();

    await waitFor(() =>
      expect(mutateMock).toHaveBeenCalledWith({
        provider_type: "openrouter",
        base_url: "https://openrouter.ai/api/v1",
        api_key: "sk-secret",
      })
    );
    // Exactly one PUT for the credentials scope, and no default_model in it.
    expect(mutateMock).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Modelo predeterminado")).toBeTruthy();
    expect(document.body.textContent).not.toContain("sk-secret");
    a.unmount();

    // A rejected PUT (SSRF guard) keeps the user on the credentials step.
    setupMocks();
    mutateMock.mockRejectedValue({
      body: { detail: { code: "invalid_base_url", message: "blocked" } },
    });
    const b = renderSetup();
    choose(CUSTOM);
    next();
    await enterKey("sk-secret");
    fireEvent.change(screen.getByLabelText("URL base"), {
      target: { value: "https://mio.example.com/v1" },
    });
    next();

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(COPY.SSRF_REJECTION)
    );
    expect(screen.getByPlaceholderText("sk-...")).toBeTruthy();
    expect(document.body.textContent).not.toContain("sk-secret");
    b.unmount();
  });

  it("restricted provider: whitelist dropdown without fetch, catalog labels, gate and empty whitelist", async () => {
    // A: the whitelist arrives with the settings; no live fetch is needed.
    setupMocks({ provider_type: "openrouter", has_api_key: true });
    const a = renderSetup();
    next();
    await screen.findByPlaceholderText("sk-...");
    next();

    const select = (await screen.findByLabelText(
      "Modelo predeterminado"
    )) as HTMLSelectElement;
    expect(select.tagName).toBe("SELECT");
    const options = Array.from(select.options).map((option) => option.textContent);
    // Labels come from the curated catalog, ids stay raw when unknown.
    expect(options).toContain("Claude Sonnet 5.5");
    expect(options).toContain("gpt-4o");
    expect(fetchModelsMock).not.toHaveBeenCalled();
    a.unmount();

    // B: a model outside the whitelist is blocked.
    setupMocks({
      provider_type: "openrouter",
      has_api_key: true,
      default_model: "openai/not-whitelisted",
      allowed_models: ["gpt-4o"],
    });
    const b = renderSetup();
    next();
    await screen.findByPlaceholderText("sk-...");
    next();
    expect(
      (
        (await screen.findByLabelText(
          "Modelo predeterminado"
        )) as HTMLSelectElement
      ).value
    ).toBe("openai/not-whitelisted");
    finish();
    expect(await screen.findByText(COPY.MODEL_NOT_ALLOWED)).toBeTruthy();
    b.unmount();

    // C: an empty whitelist must not dead-end the flow.
    setupMocks({ provider_type: "openrouter", has_api_key: true, allowed_models: [] });
    const c = renderSetup();
    next();
    await screen.findByPlaceholderText("sk-...");
    next();
    fireEvent.click(await screen.findByRole("button", { name: /Claude Sonnet 5\.5/ }));
    finish();
    await waitFor(() =>
      expect(mutateMock).toHaveBeenCalledWith({
        default_model: "anthropic/claude-sonnet-5.5",
      })
    );
    c.unmount();
  });

  it("unrestricted provider: free text, placeholders, live list and search filter", async () => {
    // A: free text accepts any non-empty value, with the Groq placeholder.
    const a = renderSetup();
    choose(GROQ);
    next();
    await enterKey("gsk-test");
    next();
    const free = (await screen.findByLabelText(
      "Modelo predeterminado"
    )) as HTMLInputElement;
    expect(free.tagName).toBe("INPUT");
    expect(free.placeholder).toBe(COPY.MODEL_PLACEHOLDERS.groq);
    fireEvent.change(free, { target: { value: "openai/gpt-oss-120b" } });
    expect(free.value).toBe("openai/gpt-oss-120b");
    a.unmount();

    // B: the placeholder is provider-specific.
    setupMocks({ provider_type: "ollama" });
    const b = renderSetup();
    next();
    await screen.findByRole("button", { name: COPY.BUTTONS.PREVIOUS });
    next();
    expect(
      (
        (await screen.findByLabelText(
          "Modelo predeterminado"
        )) as HTMLInputElement
      ).placeholder
    ).toBe(COPY.MODEL_PLACEHOLDERS.ollama);
    b.unmount();

    // C: "Cargar modelos" loads the live list, and the search box filters it.
    setupMocks(
      { provider_type: "custom", base_url: "https://mio.example.com/v1", has_api_key: true },
      [
        { id: "mio/uno", name: "Mío Uno" },
        { id: "mio/dos", name: "Mío Dos" },
      ]
    );
    const c = renderSetup();
    next();
    await screen.findByPlaceholderText("sk-...");
    next();

    const search = await screen.findByPlaceholderText(COPY.MODEL_SEARCH_PLACEHOLDER);
    fireEvent.change(search, { target: { value: "dos" } });
    const filtered = Array.from(
      (screen.getByLabelText("Modelo predeterminado") as HTMLSelectElement).options
    ).map((option) => option.textContent);
    expect(filtered).toContain("Mío Dos");
    expect(filtered).not.toContain("Mío Uno");

    fetchModelsMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: COPY.BUTTONS.LOAD_MODELS }));
    await waitFor(() => expect(fetchModelsMock).toHaveBeenCalledTimes(1));
    c.unmount();
  });

  it("a recommended card sets the model and Finalizar persists it, then probes", async () => {
    setupMocks({ provider_type: "openrouter", has_api_key: true });
    renderSetup();
    next();
    await screen.findByPlaceholderText("sk-...");
    next();

    fireEvent.click(await screen.findByRole("button", { name: /Claude Sonnet 5\.5/ }));
    expect(
      (screen.getByLabelText("Modelo predeterminado") as HTMLSelectElement).value
    ).toBe("anthropic/claude-sonnet-5.5");

    mutateMock.mockClear();
    finish();
    await waitFor(() =>
      expect(mutateMock).toHaveBeenCalledWith({
        default_model: "anthropic/claude-sonnet-5.5",
      })
    );
    // No provider_type in the model-scope payload, and the probe ran once.
    expect(fetchModelsMock).toHaveBeenCalledTimes(1);
  });

  it("result step reports a good probe, a failed probe, retries and offers the chat", async () => {
    // A: a good probe claims Connected.
    setupMocks({ provider_type: "openrouter", has_api_key: true });
    const a = renderSetup();
    next();
    await screen.findByPlaceholderText("sk-...");
    next();
    fireEvent.click(await screen.findByRole("button", { name: /Claude Sonnet 5\.5/ }));
    finish();

    expect(await screen.findByText(COPY.STATUS.CONNECTED)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ir al chat" })).toBeTruthy();
    a.unmount();

    // B: a probe error reports the honest copy plus a Retry that re-saves and re-probes.
    setupMocks({ provider_type: "openrouter", has_api_key: true }, [], {
      code: "timeout",
      message: "sin respuesta",
    });
    const b = renderSetup();
    next();
    await screen.findByPlaceholderText("sk-...");
    next();
    fireEvent.click(await screen.findByRole("button", { name: /Claude Sonnet 5\.5/ }));
    finish();

    expect(
      await screen.findByText(COPY.STATUS.UNVERIFIED("sin respuesta"))
    ).toBeTruthy();
    const retry = screen.getByRole("button", { name: COPY.BUTTONS.RETRY });
    mutateMock.mockClear();
    fetchModelsMock.mockClear();
    fireEvent.click(retry);
    await waitFor(() => expect(mutateMock).toHaveBeenCalledTimes(1));
    expect(fetchModelsMock).toHaveBeenCalledTimes(1);
    b.unmount();
  });

  it("Anterior goes back one step and clears the step error", async () => {
    renderSetup();
    choose(OPENROUTER);
    next();
    await screen.findByPlaceholderText("sk-...");
    next();
    expect(await screen.findByText(COPY.KEY_REQUIRED)).toBeTruthy();

    previous();

    expect(await screen.findByRole("radio", { name: OPENROUTER })).toBeTruthy();
    expect(screen.queryByText(COPY.KEY_REQUIRED)).toBeNull();
  });

  it("keeps Finalizar enabled after saving credentials, and the model reaches the provider", async () => {
    // Regression: persist() used to leave the status on "saving" after a
    // successful partial save. GuidedFlow derives `busy` from that status, so
    // Finalizar stayed disabled forever and the model was never saved nor
    // probed: the guided setup dead-ended on its own success.
    setupMocks({ provider_type: "openrouter", has_api_key: true });
    renderSetup();
    next();
    await screen.findByPlaceholderText("sk-...");
    next();
    await screen.findByText("Modelo predeterminado");

    const finishButton = screen.getByRole("button", {
      name: COPY.BUTTONS.FINISH,
    }) as HTMLButtonElement;
    expect(finishButton.disabled).toBe(false);

    fireEvent.change(screen.getByLabelText("Modelo predeterminado"), {
      target: { value: "gpt-4o" },
    });
    mutateMock.mockClear();
    fetchModelsMock.mockClear();
    fireEvent.click(finishButton);

    await waitFor(() => expect(mutateMock).toHaveBeenCalledTimes(1));
    expect(fetchModelsMock).toHaveBeenCalledTimes(1);
  });

  it("shows the list warning and the empty-field error together (no dedupe)", async () => {
    // The old wizard suppressed the orange warning while the red error showed.
    // They are two different facts now (the list did not arrive / the field is
    // empty) and both are worth saying. This test is the decision's witness.
    setupMocks({ provider_type: "groq" }, [], { code: "timeout", message: "sin respuesta" });
    renderSetup();
    choose(GROQ);
    next();
    await enterKey("gsk-test");
    next();

    expect(await screen.findByText(COPY.MODEL_LIST_FALLBACK)).toBeTruthy();

    finish();

    expect(await screen.findByText(COPY.MODEL_REQUIRED)).toBeTruthy();
    expect(screen.getByText(COPY.MODEL_LIST_FALLBACK)).toBeTruthy();
  });

  it("falls back to free text with the local-server hint for a keyless provider", async () => {
    setupMocks({ provider_type: "ollama" }, [], { code: "network", message: "sin red" });
    renderSetup();
    choose(OLLAMA);
    next();
    next();

    expect(await screen.findByText(COPY.MODEL_LIST_FALLBACK)).toBeTruthy();
    // The likely missing piece is the local server, so name it.
    expect(screen.getByText(COPY.MODEL_LOCAL_SERVER_HINT("Ollama"))).toBeTruthy();
    expect(screen.getByPlaceholderText(COPY.MODEL_PLACEHOLDERS.ollama)).toBeTruthy();
  });

  it("falls back to free text when the list comes back empty without an error", async () => {
    setupMocks({ provider_type: "groq" }, [], null);
    renderSetup();
    choose(GROQ);
    next();
    await enterKey("gsk-test");
    next();

    // Await the re-render: advancing a step happens inside an async handler.
    expect((await screen.findByLabelText("Modelo predeterminado")).tagName).toBe("INPUT");
    expect(screen.queryByText(COPY.MODEL_LIST_FALLBACK)).toBeNull();
  });
});
