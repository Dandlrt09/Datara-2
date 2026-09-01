import { useEffect, useRef } from "react";
import type PlotlyType from "plotly.js-dist-min";

/**
 * Lazy import of plotly.js-dist-min. Only loaded when a chart renders.
 */
let Plotly: typeof PlotlyType | null = null;

async function getPlotly(): Promise<typeof PlotlyType> {
  if (!Plotly) {
    Plotly = (await import("plotly.js-dist-min")) as unknown as typeof PlotlyType;
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
        p.react(containerRef.current, plotlyJson as unknown as PlotlyType.Data[], { responsive: true } as unknown as Partial<PlotlyType.Layout>);
      } else {
        // First render
        const data = (plotlyJson.data as PlotlyType.Data[]) ?? [];
        const layout = (plotlyJson.layout as Partial<PlotlyType.Layout>) ?? {};
        p.newPlot(containerRef.current, data, { ...layout, responsive: true } as Partial<PlotlyType.Layout>, {
          displayModeBar: true,
          responsive: true,
        } as unknown as Partial<PlotlyType.Config>);
        rendered.current = true;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [plotlyJson]);

  return <div ref={containerRef} style={{ width: "100%", minHeight: 400 }} />;
}