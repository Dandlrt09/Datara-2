import {
  INHERIT_LEVEL,
  INHERIT_LEVEL_LABEL,
  PRIVACY_LEVELS,
  PRIVACY_LEVEL_LABELS,
} from "../lib/privacy";
import type { PrivacyLevel } from "../lib/privacy";
import {
  useSessionPrivacy,
  useUpdateFilePrivacy,
} from "../queries/usePrivacy";

/** Select over the four levels. Used by the session control (no inherit). */
export function PrivacyLevelSelect({
  value,
  onChange,
  disabled,
  label,
}: {
  value: PrivacyLevel;
  onChange: (level: PrivacyLevel) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as PrivacyLevel)}
    >
      {PRIVACY_LEVELS.map((level) => (
        <option key={level} value={level}>
          {PRIVACY_LEVEL_LABELS[level]}
        </option>
      ))}
    </select>
  );
}

/**
 * Per-file override. `null` means the file inherits its session's level; the
 * row reads its own entry from the session privacy query (shared cache) to
 * show the current value.
 */
export function FilePrivacySelect({
  fileId,
  sessionId,
  filename,
  disabled,
}: {
  fileId: number;
  sessionId: string | null;
  filename: string;
  disabled?: boolean;
}) {
  const privacy = useSessionPrivacy(sessionId);
  const update = useUpdateFilePrivacy();
  const entry = privacy.data?.files.find((f) => f.file_id === fileId);
  const value = entry?.privacy_level ?? INHERIT_LEVEL;

  return (
    <select
      aria-label={`Privacidad de ${filename}`}
      value={value}
      disabled={disabled || privacy.isLoading || update.isPending}
      onChange={(e) => {
        const raw = e.target.value;
        update.mutate({
          fileId,
          privacyLevel: raw === INHERIT_LEVEL ? null : (raw as PrivacyLevel),
        });
      }}
    >
      <option value={INHERIT_LEVEL}>{INHERIT_LEVEL_LABEL}</option>
      {PRIVACY_LEVELS.map((level) => (
        <option key={level} value={level}>
          {PRIVACY_LEVEL_LABELS[level]}
        </option>
      ))}
    </select>
  );
}
