import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import type { ReactNode } from "react";
import {
  ErrorCard,
  QueryError,
  RouteErrorBoundary,
  type ErrorCardVariant,
} from "../components/ErrorCard";
import { colors } from "../design/tokens";

/**
 * jsdom normalizes hex colors to `rgb()` when inline styles are read back,
 * so rendered-color assertions convert the token hexes instead of
 * hardcoding rgb strings. The exact-hex receipt for the token values
 * themselves lives in tokens.test.ts.
 */
const rgb = (hex: string): string => {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
};

/** Per-variant expected triple straight from the design tokens. */
const VARIANT_CASES: Array<
  [ErrorCardVariant, string, string, string]
> = [
  ["error", colors.danger, colors.dangerText, colors.dangerSurface],
  ["warning", colors.warning, colors.warningText, colors.warningSurface],
  ["info", colors.info, colors.infoText, colors.infoSurface],
];

describe("ErrorCard", () => {
  beforeEach(() => {
    cleanup();
  });

  it("renders the danger treatment by default (existing consumers keep today's colors)", () => {
    render(<ErrorCard title="Something went wrong" message="boom" />);
    const card = screen.getByRole("alert");
    expect(card.style.borderColor).toBe(rgb(colors.danger));
    expect(card.style.backgroundColor).toBe(rgb(colors.dangerSurface));
    expect(
      screen.getByRole("heading").style.color,
    ).toBe(rgb(colors.dangerText));
  });

  it.each(VARIANT_CASES)(
    "renders variant %s with its token triple",
    (variant, border, heading, surface) => {
      render(<ErrorCard title="T" variant={variant} />);
      const card = screen.getByRole("alert");
      expect(card.style.borderColor).toBe(rgb(border));
      expect(card.style.backgroundColor).toBe(rgb(surface));
      expect(screen.getByRole("heading").style.color).toBe(rgb(heading));
    },
  );

  it("labels the retry button 'Retry' by default", () => {
    render(<ErrorCard title="T" onRetry={() => {}} />);
    expect(screen.getByRole("button").textContent).toBe("Retry");
  });

  it("honors an explicit actionLabel override", () => {
    render(
      <ErrorCard title="T" actionLabel="Reintentar" onRetry={() => {}} />,
    );
    expect(screen.getByRole("button").textContent).toBe("Reintentar");
  });

  it("renders no button when onRetry is absent", () => {
    render(<ErrorCard title="T" message="no action" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("wires the click to onRetry", () => {
    const onRetry = vi.fn();
    render(<ErrorCard title="T" onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("falls back to error.message when message is omitted", () => {
    render(<ErrorCard title="T" error={new Error("wrapped failure")} />);
    expect(screen.getByText("wrapped failure")).toBeTruthy();
  });
});

describe("QueryError (existing consumer)", () => {
  beforeEach(() => {
    cleanup();
  });

  it("renders the default danger card and hides children on error", () => {
    render(
      <QueryError error={new Error("load failed")} onRetry={() => {}}>
        <div>content</div>
      </QueryError>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Something went wrong")).toBeTruthy();
    expect(screen.getByText("load failed")).toBeTruthy();
    expect(screen.getByText("Retry")).toBeTruthy();
    expect(screen.queryByText("content")).toBeNull();
    // Byte-identical to the pre-change card: default danger tokens.
    const card = screen.getByRole("alert");
    expect(card.style.borderColor).toBe(rgb(colors.danger));
    expect(card.style.backgroundColor).toBe(rgb(colors.dangerSurface));
  });

  it("renders children when there is no error", () => {
    render(
      <QueryError error={null} onRetry={() => {}}>
        <div>content</div>
      </QueryError>,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("content")).toBeTruthy();
  });
});

describe("RouteErrorBoundary (existing consumer)", () => {
  function Boom(): ReactNode {
    throw new Error("route boom");
  }

  beforeEach(() => {
    cleanup();
    // React logs caught render errors via console.error; silence the
    // expected noise so test output stays clean.
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the default danger card when a child throws", () => {
    render(
      <RouteErrorBoundary viewName="Files">
        <Boom />
      </RouteErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Files Error")).toBeTruthy();
    expect(screen.getByText("route boom")).toBeTruthy();
    const card = screen.getByRole("alert");
    expect(card.style.borderColor).toBe(rgb(colors.danger));
    expect(card.style.backgroundColor).toBe(rgb(colors.dangerSurface));
  });

  it("recovers and renders children again after Retry", () => {
    const { rerender } = render(
      <RouteErrorBoundary viewName="Files">
        <Boom />
      </RouteErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    // Swap to healthy children while the boundary still holds the error
    // state (children are not rendered until the state is reset).
    rerender(
      <RouteErrorBoundary viewName="Files">
        <div>healthy</div>
      </RouteErrorBoundary>,
    );
    expect(screen.queryByText("healthy")).toBeNull();
    fireEvent.click(screen.getByText("Retry"));
    expect(screen.getByText("healthy")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
