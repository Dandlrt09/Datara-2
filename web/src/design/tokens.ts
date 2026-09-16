/**
 * Design tokens for the Datara chat UI.
 *
 * Single source of truth for the primitive style values (color palette,
 * spacing scale, typography, radii) consumed by the chat message surfaces.
 * This is the foundation for the upcoming design overhaul: every value
 * mirrors the exact literal it replaced in ChatMessage.tsx, so adopting
 * the tokens is a zero-visual-change refactor. Names describe the role a
 * value plays; the overhaul can re-map values deliberately in one place.
 */

/** Color palette grouped by role. Values are the exact literals taken from
 * the chat message surfaces (same notation as the code they replaced). */
export const colors = {
  // Light chat surfaces ------------------------------------------------
  /** Primary accent of the chat surface (user bubble background). */
  accent: "#007bff",
  /** Text rendered on top of the accent background. */
  onAccent: "#fff",
  /** Assistant message bubble background. */
  surfaceBubble: "#f0f0f0",
  /** Soft surface behind plain-text artifact previews. */
  surfaceSubtle: "#fafafa",
  /** Body text on light surfaces. */
  textPrimary: "#333",
  /** De-emphasized text (token/cost meta line). */
  textMuted: "#888",
  /** Hairline border of light artifact previews. */
  borderLight: "#e0e0e0",

  // Dark code block ------------------------------------------------------
  /** Executed-code <pre> background. */
  codeSurface: "#1e1e1e",
  /** Code block header strip background. */
  codeHeaderSurface: "#2d2d2d",
  /** Code block container border. */
  codeBorder: "#444",
  /** Executed-code text color. */
  codeText: "#e8e8e8",
  /** Language label in the code block header. */
  codeHeaderText: "#bbb",
  /** Copy button background (idle). */
  codeButtonSurface: "#3a3a3a",
  /** Copy button background (clipboard error state). */
  codeButtonSurfaceError: "#5a2d2d",
  /** Copy button label color. */
  codeButtonText: "#ddd",
} as const;

/**
 * Spacing scale in px.
 *
 * `lg` (10px) sits off the 4px grid: it is preserved from the current
 * code header / artifact paddings because the zero-visual-change
 * constraint forbids normalizing it here. Flagged for the design overhaul.
 */
export const spacing = {
  /** No spacing (resets). */
  none: 0,
  xs: 2,
  sm: 4,
  md: 8,
  /** Off-grid step (see block comment). */
  lg: 10,
  xl: 12,
  xxl: 16,
} as const;

/** Typography primitives used by the chat message surfaces. */
export const typography = {
  /** Monospace stack for executed-code surfaces. */
  fontMono: '"JetBrains Mono", ui-monospace, monospace',
  /** Relative font sizes (em) for secondary text inside messages. */
  fontSize: {
    /** Meta line, code header label, copy button. */
    xs: "0.75em",
    /** Code text, plain-text artifact preview. */
    sm: "0.85em",
  },
} as const;

/** Border radii in px, ascending. */
export const radii = {
  /** Small controls (copy button). */
  sm: 4,
  /** Inline preview panels (plain-text artifact preview). */
  md: 6,
  /** Contained blocks (code block container). */
  lg: 8,
  /** Message bubbles. */
  xl: 12,
} as const;
