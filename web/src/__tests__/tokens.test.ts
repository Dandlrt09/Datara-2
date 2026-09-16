import { describe, it, expect } from "vitest";
import { colors, radii, spacing, typography } from "../design/tokens";

/**
 * Receipt of the ChatMessage token refactor: every exported token must
 * equal the exact literal it replaced, so adopting the tokens introduced
 * zero visual change. Intentional value changes belong to the design
 * overhaul and must update these expectations deliberately.
 */
describe("design tokens (exact literals extracted from ChatMessage)", () => {
  it("keeps the chat color palette identical to the replaced literals", () => {
    expect(colors).toEqual({
      accent: "#007bff",
      onAccent: "#fff",
      surfaceBubble: "#f0f0f0",
      surfaceSubtle: "#fafafa",
      textPrimary: "#333",
      textMuted: "#888",
      borderLight: "#e0e0e0",
      codeSurface: "#1e1e1e",
      codeHeaderSurface: "#2d2d2d",
      codeBorder: "#444",
      codeText: "#e8e8e8",
      codeHeaderText: "#bbb",
      codeButtonSurface: "#3a3a3a",
      codeButtonSurfaceError: "#5a2d2d",
      codeButtonText: "#ddd",
    });
  });

  it("keeps the spacing scale identical to the replaced literals", () => {
    expect(spacing).toEqual({
      none: 0,
      xs: 2,
      sm: 4,
      md: 8,
      lg: 10,
      xl: 12,
      xxl: 16,
    });
  });

  it("keeps typography identical to the replaced literals", () => {
    expect(typography).toEqual({
      fontMono: '"JetBrains Mono", ui-monospace, monospace',
      fontSize: { xs: "0.75em", sm: "0.85em" },
    });
  });

  it("keeps the radii identical to the replaced literals", () => {
    expect(radii).toEqual({ sm: 4, md: 6, lg: 8, xl: 12 });
  });
});
