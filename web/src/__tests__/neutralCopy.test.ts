/* Guardrail for the product register: neutral Spanish with tuteo.
 *
 * S1/S2 of `odd/tasks/neutral-spanish-copy.md`: every string a person reads
 * uses "tú" — never voseo (Río de la Plata) nor formal usted. A rule without a
 * guard rots, so this test scans the `web/src` sources and fails with the file
 * and line of every forbidden marker it finds.
 *
 * The scan is textual on purpose: it strips comments and matches whole words,
 * so English identifiers and words like "nuevos" or "aviso" are not flagged.
 * Its own file is excluded, because its samples and marker list would otherwise
 * flag themselves.
 */
import { describe, it, expect } from "vitest";

/** Every source file under `web/src`, as raw text (Vite root-relative glob). */
const SOURCES = import.meta.glob("/src/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const SELF = "/src/__tests__/neutralCopy.test.ts";

/**
 * Forbidden markers (S2). The voseo set is matched case-insensitively so a
 * sentence-initial "Cerrá" or "Usá" is caught too; the usted set stays
 * case-sensitive because lowercasing would collide with English words the
 * codebase already contains ("complete", "completed").
 */
const VOSEO = new RegExp(
  "(?<![\\p{L}])(?:" +
    [
      // voseo pronouns / demonstrative
      "vos",
      "acá",
      // voseo present (vos) forms
      "tenés",
      "podés",
      "querés",
      "sos",
      "sabés",
      "hacés",
      "dejás",
      "borrás",
      // voseo imperatives
      "probá",
      "recargá",
      "revisá",
      "usá",
      "ingresá",
      "elegí",
      "repetí",
      "iniciá",
      "creá",
      "seleccioná",
      "cambiá",
      "cerrá",
      "volvé",
      "escribí",
      "mirá",
      "decime",
      "fijate",
      "tenelo",
      "tenela",
      "acordate",
      "poné",
      "dejá",
      "andá",
      "vení",
      "completá",
      "verificá",
      "apretá",
      "tocá",
      "avisame",
      "asegurate",
      "borralo",
      "reintentá",
      "dejala",
      "dejalo",
      "pegá",
      "guardá",
    ].join("|") +
    ")(?![\\p{L}])",
  "iu",
);

const USTED =
  /(?<!\p{L})(?:Elija|Ingrese|Escriba|Seleccione|Complete|Verifique|Recuerde|vuelva|téngalo)(?!\p{L})/u;

/**
 * Blanks `//` and `/* *\/` comments while preserving string literals and line
 * numbers, so a marker mentioned in a comment is not mistaken for copy.
 */
function stripComments(source: string): string {
  let out = "";
  let quote: string | null = null;
  let i = 0;
  while (i < source.length) {
    const ch = source[i];
    const next = source[i + 1];
    if (quote) {
      out += ch;
      if (ch === "\\") {
        out += next ?? "";
        i += 2;
        continue;
      }
      if (ch === quote) quote = null;
      i += 1;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      out += ch;
      i += 1;
      continue;
    }
    if (ch === "/" && next === "/") {
      while (i < source.length && source[i] !== "\n") i += 1;
      continue;
    }
    if (ch === "/" && next === "*") {
      i += 2;
      while (i < source.length && !(source[i] === "*" && source[i + 1] === "/")) {
        if (source[i] === "\n") out += "\n";
        i += 1;
      }
      i += 2;
      continue;
    }
    out += ch;
    i += 1;
  }
  return out;
}

/** Line and term of every forbidden marker in one source string. */
export function findRegisterViolations(
  source: string,
): { line: number; term: string }[] {
  const violations: { line: number; term: string }[] = [];
  stripComments(source)
    .split("\n")
    .forEach((line, index) => {
      const match = VOSEO.exec(line) ?? USTED.exec(line);
      if (match) violations.push({ line: index + 1, term: match[0] });
    });
  return violations;
}

describe("neutral copy guard (tuteo)", () => {
  it("flags the line and term of a voseo sample", () => {
    expect(
      findRegisterViolations('const a = 1;\nconst b = "Cerrá y volvé a abrir";'),
    ).toEqual([{ line: 2, term: "Cerrá" }]);
  });

  it("flags the line and term of a formal-usted sample", () => {
    expect(findRegisterViolations('const b = "Elija otra carpeta";')).toEqual([
      { line: 1, term: "Elija" },
    ]);
  });

  it("passes a neutral tuteo sample", () => {
    expect(
      findRegisterViolations(
        'const a = "Cierra y vuelve a abrir";\nconst b = "Elige otra carpeta";',
      ),
    ).toEqual([]);
  });

  it("does not trip on whole words that merely contain a marker", () => {
    expect(
      findRegisterViolations('const a = "Hay nuevos avisos"; const b = 2;'),
    ).toEqual([]);
  });

  it("does not trip on identifiers", () => {
    expect(findRegisterViolations("const vosCount = 1; const acaso = 2;")).toEqual(
      [],
    );
  });

  it("does not trip on markers mentioned in comments", () => {
    expect(
      findRegisterViolations('// cerrá esto\n/* probá luego */\nconst x = 1;'),
    ).toEqual([]);
  });

  it("keeps every user-facing string in neutral Spanish (tuteo)", () => {
    const offenders = Object.entries(SOURCES)
      .filter(([file]) => file !== SELF)
      .flatMap(([file, content]) =>
        findRegisterViolations(content).map(
          (violation) => `${file}:${violation.line}: ${violation.term}`,
        ),
      );

    expect(offenders).toEqual([]);
  });
});
