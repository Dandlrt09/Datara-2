import type { OpenBehavior } from "./preferences";

export interface LandingInput {
  /** Provider + model configured; without it the app opens settings. */
  configured: boolean;
  openBehavior: OpenBehavior;
  /** The sessions query has not resolved yet. */
  sessionsLoading: boolean;
  /** Newest session id, or null when the user has no sessions. */
  newestSessionId: string | null;
}

/**
 * Decide where `/app` lands.
 *
 * Returns the destination path, or `null` while the choice still depends on an
 * in-flight query (the caller renders Loading).
 *
 * `last_session` must WAIT for the sessions query before deciding. Deciding
 * while it was still loading fell back to the blank chat and silently ignored
 * the stored preference (verifier finding, T7a).
 */
export function landingDestination(input: LandingInput): string | null {
  if (!input.configured) return "/app/settings";
  if (input.openBehavior === "last_session") {
    if (input.sessionsLoading) return null;
    if (input.newestSessionId) return `/app/chat/${input.newestSessionId}`;
  }
  return "/app/chat";
}
