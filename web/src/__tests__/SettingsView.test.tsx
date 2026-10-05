import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SettingsView from "../routes/SettingsView";

const { useSettingsMock, mutateMock } = vi.hoisted(() => ({
  useSettingsMock: vi.fn(),
  mutateMock: vi.fn(),
}));

vi.mock("../queries/useSettings", () => ({
  useSettings: () => useSettingsMock(),
  useUpdateSettings: () => ({
    mutate: mutateMock,
    isPending: false,
    isSuccess: false,
    isError: false,
  }),
}));

describe("SettingsView", () => {
  beforeEach(() => {
    useSettingsMock.mockReset();
    mutateMock.mockReset();
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
    expect(screen.getByText("Settings")).toBeTruthy();
    expect(screen.getByPlaceholderText("sk-...")).toBeTruthy();
    // Model picker is a dropdown fed by the server whitelist
    const select = screen.getByLabelText("Default Model") as HTMLSelectElement;
    expect(select.options.length).toBe(6); // "" + 5 allowed models
    // Provider picker is a dropdown fed by the shared preset catalog
    const providerSelect = screen.getByLabelText("Provider") as HTMLSelectElement;
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
    expect(screen.getByText(/saved — leave blank to keep/i)).toBeTruthy();
    const keyInput = screen.getByPlaceholderText("sk-...") as HTMLInputElement;
    expect(keyInput.value).toBe("");
    const select = screen.getByLabelText("Default Model") as HTMLSelectElement;
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
    const providerSelect = screen.getByLabelText("Provider") as HTMLSelectElement;
    expect(providerSelect.value).toBe("openrouter");
    const baseUrlInput = screen.getByLabelText("Base URL") as HTMLInputElement;
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

    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "https://api.example.com/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText("sk-..."), {
      target: { value: "sk-new" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mutateMock).toHaveBeenCalledTimes(1));
    expect(mutateMock).toHaveBeenCalledWith(
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

    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "ollama" } });

    const baseUrlInput = screen.getByLabelText("Base URL") as HTMLInputElement;
    await waitFor(() => expect(baseUrlInput.value).toBe("http://localhost:11434/v1"));
  });

  it("shows the loading state", () => {
    useSettingsMock.mockReturnValue({ data: undefined, isLoading: true });
    render(<SettingsView />);
    expect(screen.getByText(/loading settings/i)).toBeTruthy();
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

    const baseUrlInput = screen.getByLabelText("Base URL") as HTMLInputElement;
    expect(baseUrlInput.readOnly).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /edit url/i }));
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

    const baseUrlInput = screen.getByLabelText("Base URL") as HTMLInputElement;
    expect(baseUrlInput.value).toBe("https://gateway.internal/v1");
    expect(baseUrlInput.readOnly).toBe(true);
    expect(screen.getByText(/custom url/i)).toBeTruthy();
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

    const baseUrlInput = screen.getByLabelText("Base URL") as HTMLInputElement;
    expect(baseUrlInput.readOnly).toBe(false);
    expect(screen.queryByRole("button", { name: /edit url/i })).toBeNull();
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

    const baseUrlInput = screen.getByLabelText("Base URL") as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: /edit url/i }));
    fireEvent.click(screen.getByRole("button", { name: /use default/i }));

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

    const baseUrlInput = screen.getByLabelText("Base URL") as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: /edit url/i }));
    fireEvent.change(baseUrlInput, { target: { value: "https://my-gateway.example/v1" } });
    fireEvent.click(screen.getByRole("button", { name: /^lock$/i }));

    expect(baseUrlInput.value).toBe("https://my-gateway.example/v1");
    expect(baseUrlInput.readOnly).toBe(true);
    expect(screen.getByText(/custom url/i)).toBeTruthy();
  });
});
