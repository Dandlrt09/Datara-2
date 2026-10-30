import { describe, it, expect } from "vitest";
import {
  TERMS,
  TERMS_VERSION,
  parseTerms,
  type TermsDocument,
} from "../lib/terms";

/** Every piece of visible text, lists flattened: a document is read, not walked. */
function visibleText(document: TermsDocument): string[] {
  return document.blocks.flatMap((block) =>
    block.kind === "bullets" ? block.items : [block.text],
  );
}

describe("terms documents", () => {
  it("reads the version and the date out of the Spanish metadata lines", () => {
    const document = parseTerms(
      "# Título\n\nVersión: 2.3\nÚltima actualización: 1 de enero de 2027\n\n## 1. Hola\n\nTexto.\n",
    );

    expect(document.version).toBe("2.3");
    expect(document.updated).toBe("1 de enero de 2027");
  });

  it("reads the English metadata lines with the same parser", () => {
    const document = parseTerms(
      "# Terms of Use\n\nVersion: 4.1\nLast updated: 30 October 2026\n",
    );

    expect(document.version).toBe("4.1");
    expect(document.updated).toBe("30 October 2026");
  });

  it("keeps the metadata lines out of the visible text (D3)", () => {
    const document = parseTerms(
      "Versión: 1.0\nÚltima actualización: hoy\n\n## 1. Hola\n",
    );

    expect(visibleText(document)).not.toContain("Versión: 1.0");
    expect(visibleText(document)).not.toContain("Última actualización: hoy");
  });

  it("tells the title, the headings, the paragraphs and the lists apart", () => {
    const document = parseTerms(
      "# Título\n\n## 1. Uno\n\nUn párrafo.\n\n- primero\n- segundo\n",
    );

    expect(document.blocks).toEqual([
      { kind: "title", text: "Título" },
      { kind: "heading", text: "1. Uno" },
      { kind: "paragraph", text: "Un párrafo." },
      { kind: "bullets", items: ["primero", "segundo"] },
    ]);
  });

  it("ships both languages at the same version, and that is the one sent (D5)", () => {
    expect(TERMS.en.version).toBe(TERMS.es.version);
    expect(TERMS_VERSION).toBe(TERMS.es.version);
    expect(TERMS_VERSION).toMatch(/^\d+\.\d+$/);
  });

  it("ships a real document in both languages, not an empty shell", () => {
    for (const document of [TERMS.es, TERMS.en]) {
      expect(document.blocks[0].kind).toBe("title");
      expect(
        document.blocks.filter((block) => block.kind === "heading").length,
      ).toBeGreaterThan(10);
    }
  });
});
