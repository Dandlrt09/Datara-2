import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import Setup from "../routes/Setup";
import { renderWithProviders } from "./test-utils";
import { COPY } from "../routes/setup/copy";

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
    isSuccess: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("../routes/setup/useFetchModels", () => ({
  useFetchModels: () => useFetchModelsMock(),
}));

const emptySettings = {
  user_id: 1,
  has_api_key: false,
  default_model: null,
  allowed_models: ["gpt-4o", "gpt-4o-mini"],
  provider_type: null,
  base_url: null,
};

function setupMocks(settingsOverrides: Record<string, unknown> = {}) {
  useSettingsMock.mockReset();
  mutateMock.mockReset();
  fetchModelsMock.mockReset();
  useFetchModelsMock.mockReset();

  useSettingsMock.mockReturnValue({
    data: { ...emptySettings, ...settingsOverrides },
    isLoading: false,
  });
  mutateMock.mockResolvedValue(undefined);
  fetchModelsMock.mockResolvedValue({ models: [], error: null });
  useFetchModelsMock.mockReturnValue({
    models: [],
    isLoading: false,
    error: null,
    fetchModels: fetchModelsMock,
  });
}

// Point the component's useFetchModels hook at a concrete fetch result shape.
function mockModelsState(models: unknown[], error: { code: string; message: string } | null) {
  useFetchModelsMock.mockReturnValue({
    models,
    isLoading: false,
    error: error ? new Error(error.message) : null,
    fetchModels: fetchModelsMock,
  });
}

function renderWizard() {
  return renderWithProviders(<Setup />, { route: "/app/setup" });
}

function selectPreset(label: string) {
  fireEvent.click(screen.getByLabelText(label));
}

function clickNext() {
  fireEvent.click(screen.getByText(COPY.BUTTONS.NEXT));
}

async function reachModelStep() {
  selectPreset("OpenRouter (clave de API requerida)");
  clickNext();
  const keyInput = await screen.findByPlaceholderText("sk-...");
  fireEvent.change(keyInput, { target: { value: "sk-test" } });
  clickNext();
  await screen.findByText("Modelo predeterminado");
}

async function fillFreeTextModel(value: string) {
  const input = await screen.findByPlaceholderText("gpt-4o, llama3.2:latest, etc.");
  fireEvent.change(input, { target: { value } });
}

describe("Setup", () => {
  beforeEach(() => {
    setupMocks();
  });

  it("renders the provider selection step with presets and the step indicator", () => {
    renderWizard();

    expect(screen.getByText("Configuración del proveedor")).toBeTruthy();
    COPY.STEPS.forEach((label) => {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    });
    expect(screen.getByLabelText("OpenRouter (clave de API requerida)")).toBeTruthy();
    expect(screen.getByLabelText("Ollama")).toBeTruthy();
    expect(screen.getByLabelText("LM Studio")).toBeTruthy();
    expect(screen.getByLabelText("Groq (clave de API requerida)")).toBeTruthy();
    expect(screen.getByLabelText("Custom (clave de API requerida)")).toBeTruthy();
  });

  it("blocks advancing without a provider and shows an error", async () => {
    renderWizard();

    clickNext();

    expect(await screen.findByText("Selecciona un proveedor")).toBeTruthy();
    // Still on the provider step.
    expect(screen.getByLabelText("Ollama")).toBeTruthy();
  });

  it("advances to credentials once a provider is selected", async () => {
    renderWizard();

    selectPreset("OpenRouter (clave de API requerida)");
    clickNext();

    expect(await screen.findByPlaceholderText("sk-...")).toBeTruthy();
    expect(screen.getByText("Clave de API *")).toBeTruthy();
  });

  it("blocks advancing with an empty key and shows the key-required copy", async () => {
    renderWizard();

    selectPreset("OpenRouter (clave de API requerida)");
    clickNext();
    await screen.findByPlaceholderText("sk-...");

    clickNext();

    expect(await screen.findByText(COPY.KEY_REQUIRED)).toBeTruthy();
    // Still on the credentials step.
    expect(screen.getByPlaceholderText("sk-...")).toBeTruthy();
  });

  it("requires base URL and key for the custom preset", async () => {
    renderWizard();

    selectPreset("Custom (clave de API requerida)");
    clickNext();
    await screen.findByPlaceholderText("https://...");

    clickNext();

    expect(await screen.findByText(COPY.BASE_URL_REQUIRED)).toBeTruthy();
    expect(screen.getByText(COPY.KEY_REQUIRED)).toBeTruthy();
  });

  it("resets base_url when switching presets (no stale localhost URL)", async () => {
    renderWizard();

    selectPreset("Ollama");
    clickNext();
    await waitFor(() => expect(screen.queryByLabelText("Ollama")).toBeNull());

    fireEvent.click(screen.getByText(COPY.BUTTONS.PREVIOUS));
    await waitFor(() => expect(screen.getByLabelText("Ollama")).toBeTruthy());

    selectPreset("Custom (clave de API requerida)");
    clickNext();
    const baseUrlInput = (await screen.findByPlaceholderText("https://...")) as HTMLInputElement;
    expect(baseUrlInput.value).toBe("");
  });

  it("shows a model dropdown when the model fetch succeeds", async () => {
    mockModelsState(
      [
        { id: "gpt-4o", name: "GPT-4o" },
        { id: "gpt-4o-mini", name: "GPT-4o Mini" },
      ],
      null
    );
    renderWizard();

    await reachModelStep();

    const select = await screen.findByRole("combobox");
    expect(select).toBeTruthy();
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toContain("GPT-4o");
    expect(options).toContain("GPT-4o Mini");
  });

  it("shows the free-text fallback when the model fetch fails", async () => {
    mockModelsState([], { code: "timeout", message: "timed out" });
    renderWizard();

    await reachModelStep();

    expect(await screen.findByText(COPY.MODEL_LIST_FALLBACK)).toBeTruthy();
    expect(screen.getByPlaceholderText("gpt-4o, llama3.2:latest, etc.")).toBeTruthy();
  });

  it("shows the free-text fallback when the fetched list is empty (no error)", async () => {
    renderWizard();

    await reachModelStep();

    expect(await screen.findByText(COPY.MODEL_LIST_FALLBACK)).toBeTruthy();
    expect(screen.getByPlaceholderText("gpt-4o, llama3.2:latest, etc.")).toBeTruthy();
  });

  it("uses free-text directly for the custom preset without fetching models", async () => {
    renderWizard();

    selectPreset("Custom (clave de API requerida)");
    clickNext();
    const baseUrlInput = await screen.findByPlaceholderText("https://...");
    fireEvent.change(baseUrlInput, { target: { value: "https://api.example.com/v1" } });
    const keyInput = screen.getByPlaceholderText("sk-...");
    fireEvent.change(keyInput, { target: { value: "sk-test" } });
    clickNext();

    await screen.findByPlaceholderText("gpt-4o, llama3.2:latest, etc.");
    expect(screen.queryByText(COPY.MODEL_LIST_FALLBACK)).toBeNull();
    expect(fetchModelsMock).not.toHaveBeenCalled();
  });

  it("passes the connection test, enables Finalizar, and reaches the done step", async () => {
    renderWizard();

    await reachModelStep();
    await fillFreeTextModel("gpt-4o");
    clickNext();

    // Entering the test step runs the probe automatically.
    await waitFor(() => expect(fetchModelsMock).toHaveBeenCalled());
    const finish = await screen.findByText(COPY.BUTTONS.FINISH);
    await waitFor(() => expect((finish as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(finish);

    expect(await screen.findByText(COPY.DONE_CONFIRMATION)).toBeTruthy();
    expect(screen.getByText(COPY.BUTTONS.EXIT)).toBeTruthy();
  });

  it("fails the connection test with the spec copy and passes after Reintentar", async () => {
    fetchModelsMock.mockResolvedValue({
      models: [],
      error: { code: "timeout", message: "provider timed out" },
    });
    renderWizard();

    await reachModelStep();
    await fillFreeTextModel("gpt-4o");
    clickNext();

    expect(await screen.findByText(COPY.TEST_FAILED)).toBeTruthy();
    expect(screen.getByText(COPY.BUTTONS.RETRY)).toBeTruthy();
    const finish = screen.getByText(COPY.BUTTONS.FINISH) as HTMLButtonElement;
    expect(finish.disabled).toBe(true);

    fetchModelsMock.mockResolvedValue({ models: [], error: null });
    fireEvent.click(screen.getByText(COPY.BUTTONS.RETRY));
    await waitFor(() => expect((finish as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(finish);
    expect(await screen.findByText(COPY.DONE_CONFIRMATION)).toBeTruthy();
  });

  it("shows the SSRF rejection and stays on the credentials step when save fails", async () => {
    mutateMock.mockRejectedValue({
      status: 422,
      body: {
        detail: {
          code: "invalid_base_url",
          message: "Base URL must use HTTPS and point to a public host",
        },
      },
    });
    renderWizard();

    selectPreset("Custom (clave de API requerida)");
    clickNext();
    const baseUrlInput = await screen.findByPlaceholderText("https://...");
    fireEvent.change(baseUrlInput, { target: { value: "http://localhost:8000" } });
    const keyInput = screen.getByPlaceholderText("sk-...");
    fireEvent.change(keyInput, { target: { value: "sk-test" } });

    clickNext();

    expect(await screen.findByText(COPY.SSRF_REJECTION)).toBeTruthy();
    // Still on the credentials step.
    expect(screen.getByPlaceholderText("https://...")).toBeTruthy();
  });

  it("prefills from saved settings on re-entry", () => {
    setupMocks({
      provider_type: "ollama",
      base_url: "http://localhost:11434/v1",
      default_model: "llama3",
    });
    renderWizard();

    const ollamaRadio = screen.getByLabelText("Ollama") as HTMLInputElement;
    expect(ollamaRadio.checked).toBe(true);
  });
});