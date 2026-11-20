import { useEffect, useState } from "react";
import isotipo from "../assets/datara-isotipo-animado.svg";
import "./bootSplash.css";

/**
 * How long the splash lives, in milliseconds. The isotipo is an ANIMATED SVG:
 * the artwork carries its own timeline (the nodes pop, the lines draw from
 * 1.7 s and the closing "breathe" lands at 2.75 s + 0.7 s), so the hold has to
 * outlast it or the logo is cut mid-draw. It matches the animation length in
 * `bootSplash.css` so the fade-out and the unmount land on the same frame.
 */
export const BOOT_SPLASH_MS = 3600;

/**
 * Boot splash (F4 / T3, S1 / D8): a decorative full-screen layer above the
 * router, shown on every start -- any user, any mode, and never persisted. It
 * is `aria-hidden`, has no role, no focusable content and does not trap focus,
 * so the screen underneath is fully usable; `pointerEvents: "none"` lets every
 * click through, and the same click dismisses the splash. A timer removes it
 * when the animation ends, so it never blocks the app.
 */
export function BootSplash() {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    let timer: number | null = null;
    const dismiss = () => {
      setVisible(false);
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
    };

    timer = window.setTimeout(dismiss, BOOT_SPLASH_MS);
    document.addEventListener("click", dismiss);

    return () => {
      if (timer !== null) window.clearTimeout(timer);
      document.removeEventListener("click", dismiss);
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      data-testid="boot-splash"
      aria-hidden="true"
      className="boot-splash"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f8f9fa",
        pointerEvents: "none",
      }}
    >
      <img
        src={isotipo}
        alt=""
        className="boot-splash-isotipo"
        style={{ width: 220, height: 220, objectFit: "contain" }}
      />
    </div>
  );
}
