import { useEffect, useState } from "react";
import { useSettings, useUpdateSettings } from "../queries/useSettings";
import {
  DEFAULT_PREFERENCES,
  effectivePreferences,
  type CurrencySymbol,
  type DateFormat,
  type NumberFormat,
  type OpenBehavior,
  type Preferences,
} from "../lib/preferences";
import { colors, typography } from "../design/tokens";

// Same current light inline style as the rest of ProfileView (S7 of
// profile-section): the Dark Cockpit repaint is a later work.
const cardStyle = {
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 8,
  padding: 24,
  marginBottom: 16,
} as const;

const fieldRowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 16,
  marginTop: 16,
} as const;

const labelStyle = {
  color: colors.textPrimary,
  display: "block",
} as const;

const sublabelStyle = {
  color: colors.textMuted,
  fontSize: "0.85em",
  display: "block",
} as const;

const selectStyle = {
  padding: "6px 8px",
  fontSize: 13,
  borderRadius: 6,
  border: `1px solid ${colors.borderLight}`,
  background: "#fff",
  color: colors.textPrimary,
  minWidth: 180,
} as const;

const secondaryButtonStyle = {
  padding: "6px 12px",
  fontSize: 13,
  borderRadius: 6,
  border: `1px solid ${colors.borderLight}`,
  background: "#fff",
  color: colors.textPrimary,
  cursor: "pointer",
  flexShrink: 0,
} as const;

/**
 * Display-preferences card for the Perfil screen (D5 of profile-preferences).
 *
 * It edits the four per-user preferences and saves them with the shared
 * `useUpdateSettings` mutation (which invalidates `["settings"]`, so every
 * consumer re-renders). The saved notice is deliberately small: the change is
 * reversible and the controls already show the new value.
 */
export default function PreferencesCard() {
  const { data: settings, isLoading } = useSettings();
  const update = useUpdateSettings();
  const current = effectivePreferences(settings);

  const [draft, setDraft] = useState<Preferences>(current);
  const [notice, setNotice] = useState<"saved" | "reset" | null>(null);

  // Re-sync once the stored values arrive (or change after a save) without
  // clobbering an in-progress edit: the effect only runs when a value differs.
  useEffect(() => {
    setDraft(current);
  }, [
    current.numberFormat,
    current.dateFormat,
    current.currencySymbol,
    current.openBehavior,
  ]);

  const save = (value: Preferences, notice: "saved" | "reset") => {
    setNotice(null);
    update.mutate(
      {
        number_format: value.numberFormat,
        date_format: value.dateFormat,
        currency_symbol: value.currencySymbol,
        open_behavior: value.openBehavior,
      },
      { onSuccess: () => setNotice(notice) },
    );
  };

  const handleSave = () => save(draft, "saved");

  // Restore every preference at once. This also stores the default values
  // explicitly, which is the only way to "go back" under the store's
  // "omitted means unchanged" convention.
  const handleReset = () => {
    setDraft(DEFAULT_PREFERENCES);
    save(DEFAULT_PREFERENCES, "reset");
  };

  return (
    <section style={cardStyle} aria-busy={isLoading}>
      <h2 style={{ margin: 0, color: colors.textPrimary }}>Preferencias</h2>
      <p style={{ margin: "4px 0 0", ...sublabelStyle }}>
        Se aplican al formato de la app. En el chat, cada respuesta respeta estas
        reglas.
      </p>

      <div style={fieldRowStyle}>
        <label htmlFor="pref-number-format">
          <span style={labelStyle}>Formato de números</span>
          <span style={sublabelStyle}>Cómo se muestran los separadores.</span>
        </label>
        <select
          id="pref-number-format"
          aria-label="Formato de números"
          value={draft.numberFormat}
          onChange={(e) =>
            setDraft((d) => ({ ...d, numberFormat: e.target.value as NumberFormat }))
          }
          style={selectStyle}
        >
          <option value="es">Español (1.234,56)</option>
          <option value="intl">Internacional (1,234.56)</option>
        </select>
      </div>

      <div style={fieldRowStyle}>
        <label htmlFor="pref-date-format">
          <span style={labelStyle}>Formato de fechas</span>
          <span style={sublabelStyle}>Cómo se muestran las fechas de la app.</span>
        </label>
        <select
          id="pref-date-format"
          aria-label="Formato de fechas"
          value={draft.dateFormat}
          onChange={(e) =>
            setDraft((d) => ({ ...d, dateFormat: e.target.value as DateFormat }))
          }
          style={selectStyle}
        >
          <option value="relative">Relativa (hace 2 días)</option>
          <option value="absolute">Absoluta (05/01/2024)</option>
        </select>
      </div>

      <div style={fieldRowStyle}>
        <label htmlFor="pref-currency">
          <span style={labelStyle}>Símbolo de moneda</span>
          <span style={sublabelStyle}>
            Solo el símbolo de los costos de Datara, sin conversión.
          </span>
        </label>
        <select
          id="pref-currency"
          aria-label="Símbolo de moneda"
          value={draft.currencySymbol}
          onChange={(e) =>
            setDraft((d) => ({
              ...d,
              currencySymbol: e.target.value as CurrencySymbol,
            }))
          }
          style={selectStyle}
        >
          <option value="US$">US$</option>
          <option value="$">$</option>
          <option value="USD">USD</option>
          <option value="none">Sin símbolo</option>
        </select>
      </div>

      <div style={fieldRowStyle}>
        <label htmlFor="pref-open-behavior">
          <span style={labelStyle}>Comportamiento al abrir</span>
          <span style={sublabelStyle}>Qué conversación se abre al entrar.</span>
        </label>
        <select
          id="pref-open-behavior"
          aria-label="Comportamiento al abrir"
          value={draft.openBehavior}
          onChange={(e) =>
            setDraft((d) => ({
              ...d,
              openBehavior: e.target.value as OpenBehavior,
            }))
          }
          style={selectStyle}
        >
          <option value="new_session">Nueva conversación</option>
          <option value="last_session">Última conversación</option>
        </select>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          gap: 12,
          marginTop: 20,
        }}
      >
        {notice && (
          <span
            role="status"
            style={{ color: colors.textMuted, fontSize: typography.fontSize.sm }}
          >
            {notice === "reset"
              ? "Preferencias restablecidas"
              : "Preferencias guardadas"}
          </span>
        )}
        <button
          type="button"
          onClick={handleReset}
          disabled={update.isPending}
          style={secondaryButtonStyle}
        >
          Restablecer valores por defecto
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={update.isPending}
          style={secondaryButtonStyle}
        >
          Guardar preferencias
        </button>
      </div>
    </section>
  );
}
