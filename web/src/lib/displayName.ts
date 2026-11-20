/**
 * Derive the display name shown for a user from the email address.
 *
 * Fallback for an account with no chosen name (`users.name` is NULL, D1) and
 * for legacy payloads without the field. Pure and deterministic so the profile
 * screen and the sidebar block can never disagree; `resolveDisplayName` is the
 * entry point that decides between the chosen name, this fallback and the
 * no-address default.
 */
/**
 * The neutral name shown when nothing names the account (F1/T5).
 *
 * A local profile always carries a chosen name (D5), so this is only reached
 * with partial data — a payload whose name has not loaded yet, or a malformed
 * one. It reads like a person on purpose: it is a display name, never an error
 * placeholder and never a fabricated address.
 */
const FALLBACK_DISPLAY_NAME = "Analista";

/**
 * Resolve the name to show for a user (T1/D6, F1/T5).
 *
 * Order:
 *   1. the chosen name, when it has content;
 *   2. otherwise the email-derived part, when there IS an email;
 *   3. otherwise a neutral, person-like default.
 *
 * Branch 2 is never needed for a local profile: it has no address at all
 * (`email` is null) and its name is required when it is created (D5). Branch 3
 * exists because the function is total — it is called with partial data while
 * the user loads — and it must never fabricate an address. Both the profile
 * screen and the sidebar user block call this one function, so they can never
 * print different names for the same account.
 */
export function resolveDisplayName(
  name: string | null | undefined,
  email: string | null | undefined,
): string {
  const trimmed = name?.trim();
  if (trimmed) return trimmed;
  if (email != null && email.trim().length > 0) return displayNameFromEmail(email);
  return FALLBACK_DISPLAY_NAME;
}

export function displayNameFromEmail(email: string): string {
  const trimmed = email.trim();
  const at = trimmed.indexOf("@");
  const local = at === -1 ? trimmed : trimmed.slice(0, at);
  if (local.length > 0) return local;
  return trimmed.length > 0 ? trimmed : "Cuenta";
}
