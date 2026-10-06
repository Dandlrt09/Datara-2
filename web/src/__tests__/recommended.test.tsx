import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ProviderGuide from "../routes/settings/ProviderGuide";
import {
  FREE_MODELS,
  PAID_MODELS,
  RECOMMENDED_MODELS,
  priceLabel,
} from "../routes/settings/recommended";

describe("recommended catalog", () => {
  it("ships 8 OpenRouter entries: 4 paid and 4 free", () => {
    expect(RECOMMENDED_MODELS).toHaveLength(8);
    expect(PAID_MODELS).toHaveLength(4);
    expect(FREE_MODELS).toHaveLength(4);
    expect(RECOMMENDED_MODELS.every((m) => m.provider === "openrouter")).toBe(true);
    expect(RECOMMENDED_MODELS.every((m) => m.setupUrl === "https://openrouter.ai/keys")).toBe(
      true,
    );
    expect(RECOMMENDED_MODELS.every((m) => m.guideId === "openrouter")).toBe(true);
  });

  it("marks exactly one recommended paid model and one recommended free model", () => {
    expect(PAID_MODELS.filter((m) => m.recommended)).toHaveLength(1);
    expect(FREE_MODELS.filter((m) => m.recommended)).toHaveLength(1);
    expect(PAID_MODELS.find((m) => m.recommended)?.model).toBe(
      "anthropic/claude-sonnet-5.5",
    );
    expect(FREE_MODELS.find((m) => m.recommended)?.model).toBe(
      "inclusionai/ling-3.1-flash",
    );
  });

  it("formats paid prices as input/output per 1M tokens and free as Gratis", () => {
    const paid = PAID_MODELS.find((m) => m.model === "meta/muse-spark-1.3")!;
    expect(priceLabel(paid)).toBe("Entrada $1.25 / Salida $4.25 por 1M tokens");
    const free = FREE_MODELS[0];
    expect(priceLabel(free)).toBe("Gratis");
  });
});

describe("ProviderGuide", () => {
  it("renders the OpenRouter steps and a setup link that opens in a new tab", () => {
    render(<ProviderGuide guideId="openrouter" />);

    expect(screen.getByText(/cómo configurar openrouter/i)).toBeTruthy();
    expect(screen.getByText(/crea una cuenta/i)).toBeTruthy();
    expect(screen.getByText(/pega la clave en datara/i)).toBeTruthy();

    const link = screen.getByRole("link", { name: /abrir openrouter/i });
    expect(link.getAttribute("href")).toBe("https://openrouter.ai/keys");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("renders nothing for an unknown guide id", () => {
    const { container } = render(<ProviderGuide guideId="does-not-exist" />);
    expect(container.firstChild).toBeNull();
  });
});
