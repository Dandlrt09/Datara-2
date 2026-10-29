import { colors } from "../design/tokens";

// Same current light inline style as the rest of ProfileView (the Dark Cockpit
// repaint is a later work).
const cardStyle = {
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 8,
  padding: 24,
  marginBottom: 16,
} as const;

const rowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 16,
} as const;

const rowLabelStyle = {
  color: colors.textPrimary,
  display: "block",
} as const;

const rowSublabelStyle = {
  color: colors.textMuted,
  fontSize: "0.85em",
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

/** Navigate the browser to the export endpoint. */
export const EXPORT_URL = "/api/export/account";

/**
 * Account export (T5): one button that downloads the whole account as a zip.
 *
 * The click is a real navigation, not a `fetch`: the browser streams the zip
 * straight to disk, so a multi-gigabyte export never gets buffered in a JS
 * `Blob`. The server reads the stored API key back in the same row as the
 * preferences, but the export excludes it (D3), so nothing secret is downloaded.
 */
export default function ExportAccountCard() {
  const handleExport = () => {
    window.location.assign(EXPORT_URL);
  };

  return (
    <section style={cardStyle}>
      <div style={rowStyle}>
        <div>
          <span style={rowLabelStyle}>Exportar mi cuenta</span>
          <span style={rowSublabelStyle}>
            Descarga todo en un archivo .zip
          </span>
        </div>
        <button type="button" onClick={handleExport} style={secondaryButtonStyle}>
          Descargar
        </button>
      </div>
      <p style={{ ...rowSublabelStyle, margin: "12px 0 0", lineHeight: 1.5 }}>
        El archivo incluye tus chats, tus análisis guardados, tus preferencias y
        los archivos que subiste. Puede pesar bastante y tardar unos segundos en
        empezar.
      </p>
    </section>
  );
}
