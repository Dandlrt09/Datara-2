import { describe, it, expect } from "vitest";
import { describeUserAgent } from "../lib/userAgent";

const CHROME_WINDOWS =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36";
const FIREFOX_LINUX =
  "Mozilla/5.0 (X11; Linux x86_64; rv:141.0) Gecko/20100101 Firefox/141.0";
const SAFARI_IPHONE =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const EDGE_WINDOWS =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0";
const CHROME_ANDROID =
  "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36";

describe("describeUserAgent", () => {
  it("names the browser and the platform", () => {
    expect(describeUserAgent(CHROME_WINDOWS)).toBe("Chrome en Windows");
    expect(describeUserAgent(FIREFOX_LINUX)).toBe("Firefox en Linux");
    expect(describeUserAgent(SAFARI_IPHONE)).toBe("Safari en iPhone");
    expect(describeUserAgent(CHROME_ANDROID)).toBe("Chrome en Android");
  });

  it("does not mistake a derived browser for the one it imitates", () => {
    // Edge and Android Chrome both say "Chrome ... Safari"; iOS says Safari.
    expect(describeUserAgent(EDGE_WINDOWS)).toBe("Edge en Windows");
  });

  it("says so when the agent does not name anything", () => {
    expect(describeUserAgent(null)).toBe("Dispositivo desconocido");
    expect(describeUserAgent("")).toBe("Dispositivo desconocido");
    expect(describeUserAgent("curl/8.5.0")).toBe("Dispositivo desconocido");
  });

  it("still names what it can when only one half is known", () => {
    expect(describeUserAgent("Mozilla/5.0 (Windows NT 10.0)")).toBe(
      "Navegador desconocido en Windows",
    );
    expect(describeUserAgent("Firefox/141.0")).toBe("Firefox");
  });
});
