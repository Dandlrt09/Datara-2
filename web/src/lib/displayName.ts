/**
 * Derive the display name shown for a user from the email address.
 *
 * The `users` table has no `name` column (S2), so the name is the local part
 * of the email for now; editing a real name is deferred to the login/register
 * polish. Pure and deterministic so the profile screen and the sidebar block
 * can never disagree.
 */
export function displayNameFromEmail(email: string): string {
  const trimmed = email.trim();
  const at = trimmed.indexOf("@");
  const local = at === -1 ? trimmed : trimmed.slice(0, at);
  if (local.length > 0) return local;
  return trimmed.length > 0 ? trimmed : "Cuenta";
}
