/** Name the browser and the platform behind a raw `User-Agent` string.
 *
 * The sessions list only needs to answer "which device is this?". A full agent
 * parser would be a dependency and a data-collection story this feature does
 * not have: the server stores the truncated header and never an IP (D2), and
 * the label is the only thing that leaves this file.
 *
 * Order matters in both lists, because most agents name several things: Edge
 * says "Chrome" and "Safari", Chrome says "Safari", and every browser on iOS
 * says "Safari" (Chrome there says "CriOS" instead).
 */

const UNKNOWN_DEVICE = "Dispositivo desconocido";
const UNKNOWN_BROWSER = "Navegador desconocido";

interface AgentRule {
  pattern: RegExp;
  label: string;
}

const BROWSERS: AgentRule[] = [
  { pattern: /Edg[A-Z]?\//, label: "Edge" },
  { pattern: /OPR\/|Opera/, label: "Opera" },
  { pattern: /SamsungBrowser\//, label: "Samsung Internet" },
  { pattern: /Firefox\//, label: "Firefox" },
  { pattern: /CriOS\//, label: "Chrome" },
  { pattern: /Chrome\//, label: "Chrome" },
  { pattern: /Safari\//, label: "Safari" },
];

const PLATFORMS: AgentRule[] = [
  { pattern: /iPad/, label: "iPad" },
  { pattern: /iPhone|iPod/, label: "iPhone" },
  { pattern: /Android/, label: "Android" },
  { pattern: /Windows/, label: "Windows" },
  { pattern: /CrOS/, label: "ChromeOS" },
  { pattern: /Macintosh|Mac OS X/, label: "macOS" },
  { pattern: /Linux/, label: "Linux" },
];

function firstMatch(rules: AgentRule[], value: string): string | null {
  for (const rule of rules) {
    if (rule.pattern.test(value)) return rule.label;
  }
  return null;
}

/**
 * Return a short human label for a stored user agent, e.g. `"Chrome en
 * Windows"`.
 *
 * Everything the header does not say is left out rather than guessed: a missing
 * or unrecognized agent (an empty column, a scripted client) reads as
 * "Dispositivo desconocido", never as a raw header dump.
 */
export function describeUserAgent(userAgent: string | null | undefined): string {
  if (!userAgent) return UNKNOWN_DEVICE;

  const browser = firstMatch(BROWSERS, userAgent);
  const platform = firstMatch(PLATFORMS, userAgent);

  if (browser && platform) return `${browser} en ${platform}`;
  if (browser) return browser;
  if (platform) return `${UNKNOWN_BROWSER} en ${platform}`;
  return UNKNOWN_DEVICE;
}
