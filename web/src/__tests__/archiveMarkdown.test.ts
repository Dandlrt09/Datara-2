import { describe, it, expect } from "vitest";
import {
  archiveToMarkdown,
  archiveMarkdownFilename,
} from "../lib/archiveMarkdown";

const FULL_PAYLOAD = {
  session: { title: "Análisis Q3" },
  message_count: 2,
  files: [{ filename: "ventas.csv", format: "csv", row_count: 1000 }],
  messages: [
    { role: "user", content_text: "¿Cuál fue el margen?" },
    {
      role: "assistant",
      content_text: "El margen fue del 20%.",
      code: "df = df.groupby('region').sum()",
      artifacts: [
        {
          kind: "table",
          name: "df_resumen",
          payload: {
            columns: ["región", "margen"],
            rows: [
              ["a|b", 0.2],
              ["c\nd", 0.3],
            ],
            total_rows: 5,
          },
        },
        { kind: "figure", name: "fig", payload: {} },
        { kind: "text", name: "out", payload: { text: "stdout line" } },
      ],
    },
  ],
};

describe("archiveToMarkdown", () => {
  it("renders heading, metadata, files and the conversation", () => {
    const md = archiveToMarkdown("Margen por región", FULL_PAYLOAD);

    expect(md).toContain("# Margen por región");
    expect(md).toContain("Análisis Q3 · 2 mensajes");
    expect(md).toContain("## Archivos");
    expect(md).toContain("- ventas.csv (csv, 1000 filas)");
    expect(md).toContain("## Conversación");
    expect(md).toContain("### Usuario");
    expect(md).toContain("¿Cuál fue el margen?");
    expect(md).toContain("### Asistente");
    expect(md).toContain("El margen fue del 20%.");
  });

  it("fences assistant code as python", () => {
    const md = archiveToMarkdown("X", FULL_PAYLOAD);
    expect(md).toContain("```python");
    expect(md).toContain("df = df.groupby('region').sum()");
  });

  it("renders a table artifact with escaped pipes and newlines", () => {
    const md = archiveToMarkdown("X", FULL_PAYLOAD);
    expect(md).toContain("| región | margen |");
    expect(md).toContain("a\\|b");
    expect(md).toContain("c<br>d");
  });

  it("shows the total_rows note only when the table is truncated", () => {
    const md = archiveToMarkdown("X", FULL_PAYLOAD);
    expect(md).toContain("_Mostrando 2 de 5 filas._");
  });

  it("renders figure and text artifacts", () => {
    const md = archiveToMarkdown("X", FULL_PAYLOAD);
    expect(md).toContain("_[Gráfico]_");
    expect(md).toContain("stdout line");
  });

  it("never throws on malformed or empty payloads", () => {
    expect(() => archiveToMarkdown("X", null)).not.toThrow();
    expect(() => archiveToMarkdown("X", "not-an-object")).not.toThrow();
    expect(() => archiveToMarkdown("X", 42)).not.toThrow();
    expect(() => archiveToMarkdown("X", [])).not.toThrow();
    expect(() =>
      archiveToMarkdown("X", { files: "nope", messages: 7, session: 5 }),
    ).not.toThrow();

    // A non-object payload degrades to just the heading.
    expect(archiveToMarkdown("Solo título", null)).toBe("# Solo título\n");
  });

  it("skips malformed entries instead of rendering [object Object]", () => {
    const md = archiveToMarkdown("X", {
      files: [null, { format: "csv" }, { filename: "ok.csv" }],
      messages: [null, { role: "user" }],
    });
    expect(md).toContain("- ok.csv");
    expect(md).not.toContain("[object Object]");
  });
});

describe("archiveMarkdownFilename", () => {
  it("strips path separators and appends .md", () => {
    expect(archiveMarkdownFilename("a/b\\c:d")).toBe("a-b-c-d.md");
  });

  it("falls back to a neutral base when the name is empty", () => {
    expect(archiveMarkdownFilename("   ")).toBe("analisis.md");
  });

  it("strips trailing dots", () => {
    expect(archiveMarkdownFilename("informe...")).toBe("informe.md");
  });
});
