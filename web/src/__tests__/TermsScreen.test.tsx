import { describe, it, expect } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import TermsScreen from "../routes/TermsScreen";
import { TERMS, TERMS_VERSION } from "../lib/terms";

describe("TermsScreen", () => {
  it("shows the Spanish text and the version in force", () => {
    renderWithProviders(<TermsScreen />);

    expect(
      screen.getByRole("heading", { level: 1, name: /Términos de uso/i }),
    ).toBeTruthy();
    expect(screen.getByText(`Versión ${TERMS_VERSION} · ${TERMS.es.updated}`)).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: /Ley aplicable y jurisdicción/i }),
    ).toBeTruthy();
  });

  it("switches the whole text to English", () => {
    renderWithProviders(<TermsScreen />);

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(
      screen.getByRole("heading", { level: 1, name: /Terms of Use/i }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: /Applicable law and jurisdiction/i }),
    ).toBeTruthy();
    expect(screen.getByText(`Version ${TERMS.en.version} · ${TERMS.en.updated}`)).toBeTruthy();
  });

  it("offers the way back to the signup form", () => {
    renderWithProviders(<TermsScreen />);

    expect(
      screen.getByRole("link", { name: /volver al alta/i }).getAttribute("href"),
    ).toBe("/register");
  });
});
