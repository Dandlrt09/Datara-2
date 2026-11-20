/**
 * The guided first-boot tour (F4 / T4, S2, S3, D5).
 *
 * It walks the app's tabs, not the chat: every step names the `data-tour`
 * anchor of its sidebar entry (`AppShell` renders `nav-settings`, `nav-chat`,
 * `nav-files`, `nav-archives` and `nav-profile`) and the route to open. On
 * every step change the tour navigates through the `onGoTo` prop the shell
 * hands in, so the real section shows behind the card, while the tooltip --
 * positioned from that anchor's `getBoundingClientRect()` -- points at the
 * sidebar entry that leads there. A step whose anchor is not on screen degrades
 * to a centred card instead of pointing at nothing. The closing step sends the
 * analyst back to Ajustes to configure the API key and closes the tour there.
 *
 * Navigation is a prop, never an import: the component stays renderable without
 * a Router (the specs render it bare) and every DOM/imperative navigation still
 * lives in the shell.
 *
 * It is offered once, to a profile whose stored `tutorial_seen` is false, and
 * only from inside the signed-in shell, i.e. AFTER the lock-step gate (D1), so
 * the mandatory step and the tour never fight over the same first entry.
 * Skipping it, finishing it or pressing Escape marks it through
 * `POST /api/auth/tutorial-seen` (T1) and invalidates `me`, so it does not come
 * back (S3). A refused mark closes it for this session anyway and writes
 * nothing: the tour reappears on a later launch instead of faking the flag.
 *
 * It is also reopenable (D5): the button that used to reopen the old wizard in
 * the empty chat state now calls `openTour()`, which is how the tour can be
 * evaluated without needing a fresh profile.
 */
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import type { CSSProperties } from "react";
import { create } from "zustand";
import { useMarkTutorialSeen } from "../queries/useAuth";

/**
 * Whether the tour is on screen, and whether this app session already closed
 * the first-entry offer.
 *
 * `firstEntryClosed` is deliberately in memory only: it keeps the tour down
 * while the analyst works (no nagging), and it dies with the page so a refused
 * mark lets the tour come back on the next launch. Nothing here is the source
 * of truth for "already seen" -- that lives in the profile (S3).
 */
interface GuidedTourUiState {
  open: boolean;
  firstEntryClosed: boolean;
  openTour: () => void;
  closeTour: () => void;
}

export const useGuidedTourStore = create<GuidedTourUiState>((set) => ({
  open: false,
  firstEntryClosed: false,
  openTour: () => set({ open: true }),
  closeTour: () => set({ open: false, firstEntryClosed: true }),
}));

interface TourStep {
  /** Value of the `data-tour` attribute the step points at. */
  anchor: string;
  /** Route the step opens so its own section shows behind the card. */
  route: string;
  title: string;
  body: string;
}

/** The walk, in order. The last step is the one that finishes the tour. */
export const TOUR_STEPS: TourStep[] = [
  {
    anchor: "nav-settings",
    route: "/app/settings",
    title: "Ajustes",
    body: "Aquí configuras el proveedor, pegas tu API key y eliges el modelo por defecto: es lo primero que conviene dejar listo antes de preguntar.",
  },
  {
    anchor: "nav-chat",
    route: "/app/chat",
    title: "Chat",
    body: "Aquí conversas: escribes tu pregunta, adjuntas un CSV, TSV, XLSX o JSON y Datara responde con tablas y gráficos.",
  },
  {
    anchor: "nav-files",
    route: "/app/files",
    title: "Files",
    body: "Aquí subes y ordenas los archivos que después analizas desde el Chat.",
  },
  {
    anchor: "nav-archives",
    route: "/app/archives",
    title: "Archives",
    body: "Aquí quedan guardados los análisis que marcas como importantes, listos para volver a consultarlos.",
  },
  {
    anchor: "nav-profile",
    route: "/app/profile",
    title: "Perfil",
    body: "Aquí administras tu cuenta: tu nombre, la contraseña y, en modo local, el bloqueo del perfil.",
  },
  {
    anchor: "nav-settings",
    route: "/app/settings",
    title: "Empieza por Ajustes",
    body: "Para empezar, entra en Ajustes y configura tu API key. Te dejo ahí mismo para que continúes.",
  },
];

const TOOLTIP_WIDTH = 340;
const TOOLTIP_MARGIN = 12;
const ANCHOR_GAP = 14;
/** Rough height of the card, used only to decide above/below placement. */
const TOOLTIP_HEIGHT = 210;

/**
 * Where the card goes, from the anchor's measured rect.
 *
 * No rect means "anchor not on screen": the card is centred. Otherwise the box
 * is computed in absolute coordinates and clamped into the viewport, because a
 * step must never be unreachable:
 *
 * 1. below the anchor when the card fits there,
 * 2. above it when it fits above,
 * 3. beside it otherwise -- a full-height column like the sidebar leaves no room
 *    on either side, and that case is where the card used to end up completely
 *    off the top (the old `translateY(-100%)` overrode its own clamp, so the
 *    analyst saw a 12px strip and could neither read nor click the step).
 *
 * TOOLTIP_HEIGHT is a rough height used only to pick the side; the card also
 * caps its own height (`maxHeight` on the dialog) so a taller one stays
 * scrollable instead of running off the screen.
 */
function tooltipPosition(rect: DOMRect | null): CSSProperties {
  if (!rect || (rect.width === 0 && rect.height === 0)) {
    return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" };
  }

  const maxLeft = Math.max(TOOLTIP_MARGIN, window.innerWidth - TOOLTIP_WIDTH - TOOLTIP_MARGIN);
  const clampLeft = (value: number) => Math.min(Math.max(TOOLTIP_MARGIN, value), maxLeft);
  const maxTop = Math.max(TOOLTIP_MARGIN, window.innerHeight - TOOLTIP_HEIGHT - TOOLTIP_MARGIN);
  const clampTop = (value: number) => Math.min(Math.max(TOOLTIP_MARGIN, value), maxTop);

  const below = rect.bottom + ANCHOR_GAP;
  if (below + TOOLTIP_HEIGHT + TOOLTIP_MARGIN <= window.innerHeight) {
    return { top: below, left: clampLeft(rect.left) };
  }

  const above = rect.top - ANCHOR_GAP - TOOLTIP_HEIGHT;
  if (above >= TOOLTIP_MARGIN) {
    return { top: above, left: clampLeft(rect.left) };
  }

  const beside = rect.right + ANCHOR_GAP;
  const besideLeft =
    beside + TOOLTIP_WIDTH + TOOLTIP_MARGIN <= window.innerWidth
      ? beside
      : rect.left - ANCHOR_GAP - TOOLTIP_WIDTH;
  return { top: clampTop(rect.top + ANCHOR_GAP), left: clampLeft(besideLeft) };
}

/**
 * The tour overlay itself.
 *
 * `onClose` is owned by the shell: the component never decides visibility on
 * its own, so the first-entry gate and the manual reopen live in one place.
 * `onGoTo` is the shell's navigator, passed in so the tour can open each tab
 * without importing a Router of its own.
 */
export function GuidedTour({
  onClose,
  onGoTo,
}: {
  onClose: () => void;
  onGoTo: (route: string) => void;
}) {
  const markTutorialSeen = useMarkTutorialSeen();
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  const step = TOUR_STEPS[index];
  const isLast = index === TOUR_STEPS.length - 1;

  const close = useCallback(() => {
    // Close for this app session FIRST and mark it on the server second: a
    // refused request must never trap the analyst behind the tour, and it must
    // not fake the stored flag either -- only the server writes it, so a failed
    // mark simply lets the tour come back on a later launch (S3, D5).
    onClose();
    markTutorialSeen.mutate();
  }, [markTutorialSeen, onClose]);

  // Open the step's own section, so the walk shows the real tab behind the
  // card instead of merely talking about it. It also fires on mount: the first
  // step is Ajustes, which is where the copy tells the analyst to start.
  useEffect(() => {
    onGoTo(step.route);
  }, [onGoTo, step.route]);

  // The closing step leaves the analyst where its copy points: Ajustes, to
  // configure the API key. This is the one close that navigates; skip and
  // Escape just close.
  const finish = useCallback(() => {
    onGoTo(step.route);
    close();
  }, [close, onGoTo, step.route]);

  // Escape closes the tour like a skip: both mean "I am done with this".
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [close]);

  // Re-measure on every step change and whenever the layout moves under the
  // card (resize, scroll): a stale rect would point at where the anchor used
  // to be. Scroll is captured so it also fires from inner scroll containers.
  const measure = useCallback(() => {
    const anchor = document.querySelector<HTMLElement>(
      `[data-tour="${step.anchor}"]`,
    );
    setRect(anchor ? anchor.getBoundingClientRect() : null);
  }, [step.anchor]);

  useLayoutEffect(() => {
    measure();
  }, [measure]);

  useEffect(() => {
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [measure]);

  const hasAnchor = rect !== null && (rect.width > 0 || rect.height > 0);

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 1200 }}>
      {/* Backdrop with a hole: the huge spread shadow dims everything except
          the anchor's box, which is the spotlight. */}
      {hasAnchor && rect ? (
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            top: rect.top - 6,
            left: rect.left - 6,
            width: rect.width + 12,
            height: rect.height + 12,
            borderRadius: 8,
            boxShadow: "0 0 0 9999px rgba(15, 23, 42, 0.55)",
            outline: "2px solid #2f6fed",
            pointerEvents: "none",
          }}
        />
      ) : (
        <div
          aria-hidden="true"
          style={{ position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.55)" }}
        />
      )}

      <div
        role="dialog"
        aria-label="Recorrido guiado"
        aria-live="polite"
        style={{
          position: "fixed",
          width: TOOLTIP_WIDTH,
          maxWidth: "calc(100vw - 24px)",
          // Never taller than the viewport: if the copy ever grows, the card
          // scrolls instead of pushing its own buttons off the screen.
          maxHeight: "calc(100vh - 24px)",
          overflowY: "auto",
          background: "white",
          borderRadius: 10,
          boxShadow: "0 10px 30px rgba(15, 23, 42, 0.25)",
          padding: 16,
          zIndex: 1201,
          ...tooltipPosition(rect),
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          <span style={{ fontSize: "0.8em", color: "#666" }}>
            {`Paso ${index + 1} de ${TOUR_STEPS.length}`}
          </span>
          <button
            type="button"
            aria-label="Cerrar el recorrido"
            onClick={close}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#666",
              fontSize: "1em",
              lineHeight: 1,
              padding: 0,
            }}
          >
            ×
          </button>
        </div>

        <h2 style={{ margin: "8px 0 6px", fontSize: "1.05em" }}>{step.title}</h2>
        <p style={{ margin: "0 0 16px", color: "#444", fontSize: "0.92em" }}>
          {step.body}
        </p>

        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <button type="button" onClick={close} style={{ padding: "6px 12px" }}>
            Saltar
          </button>
          {isLast ? (
            <button
              type="button"
              onClick={finish}
              style={{ padding: "6px 14px", fontWeight: 600 }}
            >
              Terminar
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setIndex((current) => current + 1)}
              style={{ padding: "6px 14px", fontWeight: 600 }}
            >
              Siguiente
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
