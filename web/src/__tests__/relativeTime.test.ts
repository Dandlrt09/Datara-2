import { describe, it, expect } from "vitest";
import { formatRelativeTimeEs, toUtcIso } from "../lib/relativeTime";

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

/** SQLite writes `datetime('now')` as UTC with no zone designator. */
function dbShape(iso: string): string {
  return iso.slice(0, 19).replace("T", " ");
}

describe("toUtcIso", () => {
  it("marks the zone-less database shape as UTC", () => {
    expect(toUtcIso("2026-10-26 21:09:18")).toBe("2026-10-26T21:09:18Z");
    expect(toUtcIso("2026-10-26 21:09:18.500")).toBe(
      "2026-10-26T21:09:18.500Z",
    );
  });

  it("leaves a string that already carries a zone alone", () => {
    expect(toUtcIso("2026-10-26T21:09:18Z")).toBe("2026-10-26T21:09:18Z");
    expect(toUtcIso("2026-10-26T21:09:18+03:00")).toBe(
      "2026-10-26T21:09:18+03:00",
    );
    expect(toUtcIso("not-a-date")).toBe("not-a-date");
  });
});

describe("formatRelativeTimeEs with a database timestamp", () => {
  it("reads the zone-less database shape as UTC, not as local time", () => {
    // The stored value and its ISO twin are the same instant, so they must
    // read the same; before the fix the zone-less one was shifted by the local
    // offset (a row created a second ago read as hours in the future).
    const iso = ago(2 * MINUTE_MS);

    expect(formatRelativeTimeEs(dbShape(iso))).toBe(
      formatRelativeTimeEs(iso),
    );
    expect(formatRelativeTimeEs(dbShape(iso))).toBe("hace 2 minutos");
  });
});
