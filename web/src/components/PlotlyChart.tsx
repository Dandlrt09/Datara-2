import { useEffect, useRef, useState } from "react";
import type { Config, Data, Layout, PlotlyStatic } from "plotly.js-dist-min";

/**
 * Lazy import of plotly.js-dist-min. Only loaded when a chart renders.
 */
let Plotly: PlotlyStatic | null = null;

async function getPlotly(): Promise<PlotlyStatic> {
  if (!Plotly) {
    Plotly = (await import("plotly.js-dist-min")) as unknown as PlotlyStatic;
  }
  return Plotly;
}

interface PlotlyChartProps {
  plotlyJson: Record<string, unknown>;
}

export default function PlotlyChart({ plotlyJson }: PlotlyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendered = useRef(false);
  // Last width we re-fitted to: a ResizeObserver re-report at the same width
  // must not trigger another resize (that would be a feedback loop).
  const lastWidth = useRef(0);
  // True once the figure is actually plotted: the export button is
  // meaningless (and toImage would reject) before that.
  const [ready, setReady] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const p = await getPlotly();
      if (cancelled || !containerRef.current) return;
      if (rendered.current) {
        // Already rendered: use Plotly.react for updates
        p.react(containerRef.current, plotlyJson as unknown as Data[], {
          responsive: true,
        } as unknown as Partial<Layout>);
      } else {
        // First render
        const data = (plotlyJson.data as Data[]) ?? [];
        const layout = (plotlyJson.layout as Partial<Layout>) ?? {};
        p.newPlot(
          containerRef.current,
          data,
          { ...layout, responsive: true } as Partial<Layout>,
          {
            displayModeBar: true,
            responsive: true,
          } as unknown as Partial<Config>,
        );
        rendered.current = true;
        setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [plotlyJson]);

  // Re-fit the figure when the CONTAINER's width changes without a window
  // resize: a sidebar/panel toggle, or a browser page-zoom excursion. plotly's
  // own `responsive` listens only to window resizes, so without this the plot
  // keeps a stale pixel width, overflows its parent forever, and (through the
  // flex column's automatic minimum size) leaves the whole chat wider than the
  // viewport with a horizontal scrollbar.
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width <= 0 || Math.abs(width - lastWidth.current) < 1) return;
      lastWidth.current = width;
      if (!rendered.current || !Plotly) return;
      Plotly.Plots.resize(el);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  /** Export the current figure as a PNG data URL and trigger a download. */
  async function handleDownloadPng() {
    if (!containerRef.current || !Plotly || exporting) return;
    setExporting(true);
    try {
      const dataUrl = await Plotly.toImage(containerRef.current, {
        format: "png",
        scale: 2,
      });
      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = "datara-grafico.png";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch {
      // toImage rejected (e.g. plotly not ready) — do nothing, never crash.
    } finally {
      setExporting(false);
    }
  }

  return (
    <div style={{ width: "100%" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: 4,
        }}
      >
        <button
          onClick={handleDownloadPng}
          disabled={!ready || exporting}
          style={{
            background: "#fff",
            color: "#555",
            border: "1px solid #ccc",
            borderRadius: 4,
            cursor: ready && !exporting ? "pointer" : "default",
            fontSize: "0.75em",
            padding: "2px 8px",
          }}
          title="Descarga el gráfico como imagen PNG"
        >
          Descargar PNG
        </button>
      </div>
      <div
        ref={containerRef}
        data-testid="plotly-chart"
        style={{ width: "100%", minHeight: 400, overflow: "hidden" }}
      />
    </div>
  );
}
