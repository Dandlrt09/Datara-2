import { useEffect, useRef } from "react";
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
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [plotlyJson]);

  return <div ref={containerRef} style={{ width: "100%", minHeight: 400 }} />;
}
