/**
 * Derive the display name shown for a user from the email address.
 *
 * Fallback for an account with no chosen name (`users.name` is NULL, D1) and
 * for legacy payloads without the field. Pure and deterministic so the profile
 * screen and the sidebar block can never disagree; `resolveDisplayName` is the
 * entry point that decides between the chosen name and this fallback.
 */
/**
 * Resolve the name to show for a user (T1/D6).
 *
 * The chosen name wins when it has content; otherwise the email-derived name
 * takes over, which is also what a brand-new account shows. Both the profile
 * screen and the sidebar user block call this one function, so they can never
 * print different names for the same account.
 */
export function resolveDisplayName(
  name: string | null | undefined,
  email: string,
): string {
  const trimmed = name?.trim();
  if (trimmed) return trimmed;
  return displayNameFromEmail(email);
}

export function displayNameFromEmail(email: string): string {
  const trimmed = email.trim();
  const at = trimmed.indexOf("@");
  const local = at === -1 ? trimmed : trimmed.slice(0, at);
  if (local.length > 0) return local;
  return trimmed.length > 0 ? trimmed : "Cuenta";
}
