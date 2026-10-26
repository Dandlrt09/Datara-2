import { describe, it, expect } from "vitest";
import { landingDestination } from "../lib/landing";

describe("landingDestination (open_behavior)", () => {
  it("sends an unconfigured app to settings", () => {
    expect(
      landingDestination({
        configured: false,
        openBehavior: "last_session",
        sessionsLoading: false,
        newestSessionId: "s1",
      }),
    ).toBe("/app/settings");
  });

  it("waits for the sessions query before honoring last_session", () => {
    // Regression: deciding while sessions were still in flight silently fell
    // back to the blank chat and ignored the stored preference.
    expect(
      landingDestination({
        configured: true,
        openBehavior: "last_session",
        sessionsLoading: true,
        newestSessionId: "s1",
      }),
    ).toBeNull();
  });

  it("opens the newest session once the sessions resolve", () => {
    expect(
      landingDestination({
        configured: true,
        openBehavior: "last_session",
        sessionsLoading: false,
        newestSessionId: "s1",
      }),
    ).toBe("/app/chat/s1");
  });

  it("falls back to the blank chat when last_session has no sessions", () => {
    expect(
      landingDestination({
        configured: true,
        openBehavior: "last_session",
        sessionsLoading: false,
        newestSessionId: null,
      }),
    ).toBe("/app/chat");
  });

  it("keeps today's blank-chat default for new_session", () => {
    expect(
      landingDestination({
        configured: true,
        openBehavior: "new_session",
        sessionsLoading: false,
        newestSessionId: "s1",
      }),
    ).toBe("/app/chat");
  });
});
