import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import PlotlyChart from "../components/PlotlyChart";

// The component lazy-imports plotly.js-dist-min; intercept the dynamic import
// with a lightweight fake PlotlyStatic so no real plotly runs in jsdom.
vi.mock("plotly.js-dist-min", () => ({
  newPlot: vi.fn().mockResolvedValue(undefined),
  react: vi.fn().mockResolvedValue(undefined),
  toImage: vi.fn().mockResolvedValue("data:image/png;base64,AAAA"),
}));

const plotly = (await import("plotly.js-dist-min")) as unknown as {
  newPlot: ReturnType<typeof vi.fn>;
  react: ReturnType<typeof vi.fn>;
  toImage: ReturnType<typeof vi.fn>;
};

const FIGURE = {
  data: [{ type: "bar", x: ["a"], y: [1] }],
  layout: {},
};

describe("PlotlyChart PNG download", () => {
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    plotly.newPlot.mockClear();
    plotly.react.mockClear();
    plotly.toImage.mockClear();
    plotly.toImage.mockResolvedValue("data:image/png;base64,AAAA");
    clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
  });

  afterEach(() => {
    clickSpy.mockRestore();
  });

  it("renders the figure, the Descargar PNG button, and exports on click", async () => {
    render(<PlotlyChart plotlyJson={FIGURE} />);

    await waitFor(() => expect(plotly.newPlot).toHaveBeenCalled());
    const button = screen.getByText("Descargar PNG") as HTMLButtonElement;
    // Disabled until the figure is actually plotted.
    await waitFor(() => expect(button.disabled).toBe(false));

    fireEvent.click(button);

    await waitFor(() => expect(clickSpy).toHaveBeenCalled());
    expect(plotly.toImage).toHaveBeenCalledTimes(1);
    const [graphDiv, options] = plotly.toImage.mock.calls[0];
    expect(graphDiv).toBe(screen.getByTestId("plotly-chart"));
    expect(options).toMatchObject({ format: "png", scale: 2 });

    const anchor = clickSpy.mock.contexts[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("datara-grafico.png");
    expect(anchor.href).toBe("data:image/png;base64,AAAA");
  });

  it("does not crash when toImage rejects", async () => {
    plotly.toImage.mockRejectedValue(new Error("export failed"));
    render(<PlotlyChart plotlyJson={FIGURE} />);

    await waitFor(() => expect(plotly.newPlot).toHaveBeenCalled());
    await waitFor(() =>
      expect(
        (screen.getByText("Descargar PNG") as HTMLButtonElement).disabled,
      ).toBe(false),
    );

    fireEvent.click(screen.getByText("Descargar PNG"));

    // Let the rejection settle: nothing should throw and the button should
    // recover to its enabled idle state.
    await waitFor(() =>
      expect(
        (screen.getByText("Descargar PNG") as HTMLButtonElement).disabled,
      ).toBe(false),
    );
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it("ignores clicks while an export is already in flight", async () => {
    let resolveImage: (v: string) => void = () => {};
    plotly.toImage.mockReturnValue(
      new Promise<string>((res) => {
        resolveImage = res;
      }),
    );

    render(<PlotlyChart plotlyJson={FIGURE} />);
    await waitFor(() => expect(plotly.newPlot).toHaveBeenCalled());
    const button = screen.getByText("Descargar PNG") as HTMLButtonElement;
    await waitFor(() => expect(button.disabled).toBe(false));

    fireEvent.click(button);
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(plotly.toImage).toHaveBeenCalledTimes(1);

    resolveImage("data:image/png;base64,BBBB");
    await waitFor(() => expect(button.disabled).toBe(false));
  });
});
