import { useActivity, type ActivityEvent } from "../queries/useActivity";
import {
  formatNumber,
  formatTimestamp,
  usePreferences,
} from "../lib/preferences";
import { colors } from "../design/tokens";

// Same current light inline style as the rest of ProfileView (the Dark Cockpit
// repaint is a later work).
const cardStyle = {
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 8,
  padding: 24,
  marginBottom: 16,
} as const;

const sublabelStyle = {
  color: colors.textMuted,
  fontSize: "0.85em",
  display: "block",
} as const;

const KIND_LABEL: Record<ActivityEvent["kind"], string> = {
  chat: "Chat creado",
  file: "Archivo subido",
  archive: "Análisis guardado",
};

/**
 * Personal activity log (T6): this month's totals and the latest events.
 *
 * Everything comes from `GET /api/activity`, computed live from what exists
 * today, so a deleted chat takes its history with it (S6) — the card says so.
 */
export default function ActivityLogCard() {
  const { data, isLoading } = useActivity();
  const { dateFormat, numberFormat } = usePreferences();

  const month = data?.month;
  const events = data?.events ?? [];
  const totals: [string, number][] = month
    ? [
        ["Chats iniciados", month.chats],
        ["Análisis ejecutados", month.analyses],
        ["Archivos subidos", month.files],
        ["Filas procesadas", month.rows],
        ["Análisis guardados", month.archives],
      ]
    : [];

  return (
    <section style={cardStyle} aria-busy={isLoading}>
      <h2 style={{ margin: 0, color: colors.textPrimary }}>Bitácora</h2>
      <p style={{ margin: "4px 0 0", ...sublabelStyle }}>
        Tu actividad de este mes. Refleja lo que existe hoy: si borrás un chat,
        también desaparece de acá.
      </p>

      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 12,
          margin: "16px 0 0",
        }}
      >
        {totals.map(([label, value]) => (
          <div key={label}>
            <dt style={sublabelStyle}>{label}</dt>
            <dd
              style={{
                margin: 0,
                color: colors.textPrimary,
                fontSize: "1.25em",
              }}
            >
              {formatNumber(value, numberFormat)}
            </dd>
          </div>
        ))}
      </dl>

      <h3 style={{ margin: "20px 0 0", color: colors.textPrimary }}>
        Últimos movimientos
      </h3>
      {!isLoading && events.length === 0 && (
        <p style={{ ...sublabelStyle, marginTop: 8 }}>
          Todavía no hay actividad.
        </p>
      )}
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {events.map((event, index) => (
          <li
            key={`${event.kind}-${event.at}-${index}`}
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: 16,
              marginTop: 12,
            }}
          >
            <div>
              <span style={{ color: colors.textPrimary, display: "block" }}>
                {event.title}
              </span>
              <span style={sublabelStyle}>{KIND_LABEL[event.kind]}</span>
            </div>
            <span style={{ ...sublabelStyle, flexShrink: 0 }}>
              {formatTimestamp(event.at, dateFormat)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
