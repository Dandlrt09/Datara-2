import { describe, it, expect } from "vitest";
import { formatNumberEs, formatTableValue } from "../lib/formatNumbers";

describe("formatNumberEs", () => {
  it("groups the integer part with dots and uses a comma decimal", () => {
    expect(formatNumberEs(1234567.5)).toBe("1.234.567,5");
  });

  it("renders at most the requested fraction digits", () => {
    expect(formatNumberEs(1.23456789, 2)).toBe("1,23");
  });

  it("strips trailing zeros in the fraction", () => {
    expect(formatNumberEs(5020000)).toBe("5.020.000");
    expect(formatNumberEs(5.5)).toBe("5,5");
  });

  it("renders -0 as 0, never -0", () => {
    expect(formatNumberEs(-0)).toBe("0");
    expect(formatNumberEs(-0.0000001)).toBe("0");
  });

  it("renders a negative number with its sign", () => {
    expect(formatNumberEs(-1234.25)).toBe("-1.234,25");
  });

  it("renders non-finite values as an em dash", () => {
    expect(formatNumberEs(NaN)).toBe("—");
    expect(formatNumberEs(Infinity)).toBe("—");
    expect(formatNumberEs(-Infinity)).toBe("—");
  });
});

describe("formatTableValue", () => {
  it("renders null and undefined as an em dash", () => {
    expect(formatTableValue(null)).toBe("—");
    expect(formatTableValue(undefined)).toBe("—");
  });

  it("formats numbers with the Spanish convention", () => {
    expect(formatTableValue(1234.5)).toBe("1.234,5");
  });

  it("passes non-number values through as strings", () => {
    expect(formatTableValue("hola")).toBe("hola");
    expect(formatTableValue(true)).toBe("true");
  });
});
