// Minimal ambient declaration: plotly.js-dist-min ships no bundled types.
// Only the surface consumed by PlotlyChart.tsx is declared; anything richer
// should come from @types/plotly.js when the design overhaul lands.
declare module "plotly.js-dist-min" {
  export interface Data {
    [key: string]: unknown;
  }
  export type Layout = Record<string, unknown>;
  export type Config = Record<string, unknown>;

  export interface PlotlyStatic {
    react(...args: unknown[]): unknown;
    newPlot(...args: unknown[]): unknown;
    [key: string]: unknown;
  }

  const Plotly: PlotlyStatic;
  export default Plotly;
}
