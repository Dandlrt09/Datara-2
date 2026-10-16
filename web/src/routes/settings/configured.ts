// Whether Datara can answer at all: a provider and a model are stored.
//
// Two places need this answer — the settings engine (which opens the guided
// flow when the app is not configured) and the `/app` landing in AppShell — and
// a rule written twice is how the two drift apart. That is the whole reason
// this file exists instead of an inline expression in each.
//
// A stored API key is deliberately not part of it: the server falls back to the
// OPENAI_API_KEY environment variable, which the client cannot see, so "no key
// stored" is not the same as "not configured" — gating on it would lock out a
// working deployment.

import type { UserSettings } from "../../queries/useSettings";

export function isProviderConfigured(settings: UserSettings | undefined): boolean {
  return Boolean(settings?.provider_type && settings?.default_model);
}
