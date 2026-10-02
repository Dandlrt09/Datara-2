import { describe, it, expect } from "vitest";
import { formatRelativeTimeEs } from "../lib/relativeTime";

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

function ago(ms: number): string {
  return new Date(Date.now() - ms).toISOString();
}

describe("formatRelativeTimeEs", () => {
  it("formats days, weeks and hours in neutral Spanish", () => {
    expect(formatRelativeTimeEs(ago(5 * DAY_MS))).toBe("hace 5 días");
    expect(formatRelativeTimeEs(ago(3 * 7 * DAY_MS))).toBe("hace 3 semanas");
    expect(formatRelativeTimeEs(ago(2 * HOUR_MS))).toBe("hace 2 horas");
    expect(formatRelativeTimeEs(ago(30 * MINUTE_MS))).toBe("hace 30 minutos");
  });

  it("always uses the numeric phrasing from the design", () => {
    expect(formatRelativeTimeEs(ago(2 * DAY_MS))).toBe("hace 2 días");
    expect(formatRelativeTimeEs(ago(7 * DAY_MS))).toBe("hace 1 semana");
  });

  it("reads a just-created date as 'hace un momento'", () => {
    expect(formatRelativeTimeEs(ago(0))).toBe("hace un momento");
  });

  it("falls back to toLocaleDateString on an invalid date", () => {
    const invalid = "not-a-date";
    expect(formatRelativeTimeEs(invalid)).toBe(
      new Date(invalid).toLocaleDateString(),
    );
  });
});
