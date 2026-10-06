import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ProviderGuide from "../routes/settings/ProviderGuide";
import {
  catalogFor,
  modelsForProvider,
  priceLabel,
  RECOMMENDED_MODELS,
} from "../routes/settings/recommended";

describe("recommended catalog", () => {
  it("ships 8 OpenRouter entries and 3 Groq entries", () => {
    expect(RECOMMENDED_MODELS).toHaveLength(11);
    expect(modelsForProvider("openrouter")).toHaveLength(8);
    expect(modelsForProvider("groq")).toHaveLength(3);
    // Providers without a curated catalog return none.
    expect(modelsForProvider("ollama")).toHaveLength(0);
    expect(modelsForProvider("lmstudio")).toHaveLength(0);
    expect(modelsForProvider("custom")).toHaveLength(0);
    expect(modelsForProvider(undefined)).toHaveLength(0);
  });

  it("keys every entry to its provider, setup URL and guide", () => {
    for (const m of modelsForProvider("openrouter")) {
      expect(m.provider).toBe("openrouter");
      expect(m.setupUrl).toBe("https://openrouter.ai/keys");
      expect(m.guideId).toBe("openrouter");
    }
    for (const m of modelsForProvider("groq")) {
      expect(m.provider).toBe("groq");
      expect(m.setupUrl).toBe("https://console.groq.com/keys");
      expect(m.guideId).toBe("groq");
    }
  });

  it("splits the provider catalog by tier and leaves empty tiers empty", () => {
    const openrouter = catalogFor("openrouter");
    expect(openrouter.paid).toHaveLength(4);
    expect(openrouter.free).toHaveLength(4);

    // Groq has no free tier.
    const groq = catalogFor("groq");
    expect(groq.paid).toHaveLength(3);
    expect(groq.free).toHaveLength(0);

    const none = catalogFor("lmstudio");
    expect(none.paid).toHaveLength(0);
    expect(none.free).toHaveLength(0);
  });

  it("marks exactly one recommended Groq model and keeps its real prices", () => {
    const groq = modelsForProvider("groq");
    expect(groq.filter((m) => m.recommended)).toHaveLength(1);
    expect(groq.find((m) => m.recommended)?.model).toBe("openai/gpt-oss-120b");

    const gpt120 = groq.find((m) => m.model === "openai/gpt-oss-120b")!;
    expect(gpt120.inputUsdPerMillion).toBe(0.15);
    expect(gpt120.outputUsdPerMillion).toBe(0.6);
    expect(priceLabel(gpt120)).toBe("Entrada $0.15 / Salida $0.60 por 1M tokens");

    const gpt20 = groq.find((m) => m.model === "openai/gpt-oss-20b")!;
    expect(gpt20.inputUsdPerMillion).toBe(0.075);
    expect(gpt20.outputUsdPerMillion).toBe(0.3);
    // JS (0.075).toFixed(2) is "0.07" (binary float); the stored rate is exact.
    expect(priceLabel(gpt20)).toBe("Entrada $0.07 / Salida $0.30 por 1M tokens");

    const qwen = groq.find((m) => m.model === "qwen/qwen3.8-27b")!;
    expect(qwen.label).toContain("preview");
    expect(qwen.inputUsdPerMillion).toBe(0.8);
    expect(qwen.outputUsdPerMillion).toBe(4.0);
    expect(priceLabel(qwen)).toBe("Entrada $0.80 / Salida $4.00 por 1M tokens");
  });

  it("marks exactly one recommended OpenRouter paid and one free model", () => {
    const openrouter = catalogFor("openrouter");
    expect(openrouter.paid.filter((m) => m.recommended)).toHaveLength(1);
    expect(openrouter.free.filter((m) => m.recommended)).toHaveLength(1);
    expect(openrouter.paid.find((m) => m.recommended)?.model).toBe(
      "anthropic/claude-sonnet-5.5",
    );
    expect(openrouter.free.find((m) => m.recommended)?.model).toBe(
      "inclusionai/ling-3.1-flash",
    );
  });

  it("formats paid prices as input/output per 1M tokens and free as Gratis", () => {
    const paid = modelsForProvider("openrouter").find(
      (m) => m.model === "meta/muse-spark-1.3",
    )!;
    expect(priceLabel(paid)).toBe("Entrada $1.25 / Salida $4.25 por 1M tokens");
    const free = catalogFor("openrouter").free[0];
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

  it("renders the Groq guide and its setup link", () => {
    render(<ProviderGuide guideId="groq" />);

    expect(screen.getByText(/cómo configurar groq/i)).toBeTruthy();
    expect(screen.getByText(/genera una clave de api/i)).toBeTruthy();
    const link = screen.getByRole("link", { name: /abrir consola de groq/i });
    expect(link.getAttribute("href")).toBe("https://console.groq.com/keys");
    expect(link.getAttribute("target")).toBe("_blank");
  });

  it("renders the Ollama guide with no API key step and a download link", () => {
    render(<ProviderGuide guideId="ollama" />);

    expect(screen.getByText(/cómo configurar ollama/i)).toBeTruthy();
    expect(screen.getByText(/no hace falta clave de api/i)).toBeTruthy();
    expect(screen.getAllByText(/servidor local/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /descargar ollama/i }).getAttribute("href")).toBe(
      "https://ollama.com/download",
    );
  });

  it("renders the LM Studio guide with its server steps and link", () => {
    render(<ProviderGuide guideId="lmstudio" />);

    expect(screen.getByText(/cómo configurar lm studio/i)).toBeTruthy();
    expect(screen.getAllByText(/servidor/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /abrir lm studio/i }).getAttribute("href")).toBe(
      "https://lmstudio.ai/",
    );
  });

  it("renders the custom guide with no external link", () => {
    const { container } = render(<ProviderGuide guideId="custom" />);

    expect(screen.getByText(/cómo configurar un proveedor compatible/i)).toBeTruthy();
    expect(screen.getByText(/url base que termina en \/v1/i)).toBeTruthy();
    expect(container.querySelector("a")).toBeNull();
  });

  it("renders nothing for an unknown guide id", () => {
    const { container } = render(<ProviderGuide guideId="does-not-exist" />);
    expect(container.firstChild).toBeNull();
  });
});
