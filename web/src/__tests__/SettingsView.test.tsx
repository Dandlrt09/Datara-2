import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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
      data: { user_id: 1, has_api_key: false, default_model: null },
      isLoading: false,
    });
    render(<SettingsView />);
    expect(screen.getByText("Settings")).toBeTruthy();
    expect(screen.getByPlaceholderText("sk-...")).toBeTruthy();
    expect(screen.getByPlaceholderText("gpt-4o-2024-08-06")).toBeTruthy();
  });

  it("keeps the key input empty and shows the saved badge", () => {
    useSettingsMock.mockReturnValue({
      data: { user_id: 1, has_api_key: true, default_model: "gpt-4o" },
      isLoading: false,
    });
    render(<SettingsView />);
    expect(screen.getByText(/saved — leave blank to keep/i)).toBeTruthy();
    const keyInput = screen.getByPlaceholderText("sk-...") as HTMLInputElement;
    expect(keyInput.value).toBe("");
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
});