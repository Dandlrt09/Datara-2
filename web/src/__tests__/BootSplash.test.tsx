import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { screen, fireEvent, act } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";

/* F4 / T3 (S1, D8): the boot splash is a decorative overlay above the router.
 * It shows on every start, dismisses itself when the animation ends or on a
 * click anywhere, and stays out of the accessibility tree so the screens
 * underneath keep answering role queries. */
import { BootSplash, BOOT_SPLASH_MS } from "../components/BootSplash";

describe("BootSplash (F4 / T3)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the isotipo as soon as the app mounts", () => {
    renderWithProviders(<BootSplash />);

    const splash = screen.getByTestId("boot-splash");
    const isotipo = splash.querySelector("img");
    expect(isotipo).not.toBeNull();
    expect(isotipo?.getAttribute("src")).toContain("datara-isotipo");
  });

  it("does not hide the app it is drawn over", () => {
    renderWithProviders(
      <>
        <BootSplash />
        <div>app-content</div>
      </>,
    );

    // The overlay is a sibling layer: the app renders underneath it at once.
    expect(screen.getByText("app-content")).toBeTruthy();
    expect(screen.getByTestId("boot-splash")).toBeTruthy();
  });

  it("skips immediately on a click anywhere", () => {
    renderWithProviders(<BootSplash />);
    expect(screen.getByTestId("boot-splash")).toBeTruthy();

    fireEvent.click(document.body);

    expect(screen.queryByTestId("boot-splash")).toBeNull();
  });

  it("goes away by itself once the animation ends", () => {
    renderWithProviders(<BootSplash />);
    expect(screen.getByTestId("boot-splash")).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(BOOT_SPLASH_MS + 50);
    });

    expect(screen.queryByTestId("boot-splash")).toBeNull();
  });

  it("is decorative: aria-hidden, no role and nothing focusable", () => {
    renderWithProviders(<BootSplash />);

    const splash = screen.getByTestId("boot-splash");
    expect(splash.getAttribute("aria-hidden")).toBe("true");
    expect(splash.getAttribute("role")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
    expect(
      splash.querySelectorAll("button, a, input, select, textarea, [tabindex]"),
    ).toHaveLength(0);
  });

  it("clears its timer on unmount", () => {
    const clear = vi.spyOn(globalThis, "clearTimeout");
    const { unmount } = renderWithProviders(<BootSplash />);

    unmount();

    expect(clear).toHaveBeenCalled();
    clear.mockRestore();
  });
});
