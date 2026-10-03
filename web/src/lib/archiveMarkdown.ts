/**
 * Pure Markdown serializer for an archived analysis snapshot.
 *
 * `archiveToMarkdown` is intentionally total: any malformed payload degrades
 * to whatever is readable and never throws, because it runs straight from a
 * stored JSON blob that may predate the current schema.
 */

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/** Escape a single Markdown table cell: pipes break the row, newlines break
 * the table. Newlines collapse to a `<br>` so line intent survives. */
function escapeTableCell(value: unknown): string {
  if (value == null) return "";
  return String(value).replace(/\|/g, "\\|").replace(/\r?\n/g, "<br>");
}

/** Render one `kind: "table"` artifact payload as a Markdown table. */
function tableToMarkdown(payload: Record<string, unknown>): string[] {
  const columns = asArray(payload.columns).filter(
    (c): c is string => typeof c === "string",
  );
  if (columns.length === 0) return [];
  const rows = asArray(payload.rows);

  const lines: string[] = [
    `| ${columns.map(escapeTableCell).join(" | ")} |`,
    `| ${columns.map(() => "---").join(" | ")} |`,
  ];
  for (const row of rows) {
    const cells = Array.isArray(row) ? row : [];
    lines.push(
      `| ${columns.map((_, i) => escapeTableCell(cells[i])).join(" | ")} |`,
    );
  }

  const total = payload.total_rows;
  if (typeof total === "number" && total > rows.length) {
    lines.push("", `_Mostrando ${rows.length} de ${total} filas._`);
  }
  return lines;
}

/** Render one message's `artifacts[]` as Markdown blocks. Unknown shapes are
 * skipped, never serialized as `[object Object]`. */
function artifactsToMarkdown(raw: unknown): string[] {
  const lines: string[] = [];
  for (const artifact of asArray(raw)) {
    const art = asRecord(artifact);
    if (!art) continue;
    const payload = asRecord(art.payload);

    if (art.kind === "table" && payload) {
      const table = tableToMarkdown(payload);
      if (table.length > 0) lines.push(...table, "");
    } else if (art.kind === "figure") {
      lines.push("_[Gráfico]_", "");
    } else if (art.kind === "text") {
      const text = typeof payload?.text === "string" ? payload.text : "";
      lines.push("```", text, "```", "");
    }
  }
  return lines;
}

/**
 * Serialize a stored archive snapshot to a Markdown document.
 *
 * A non-object payload yields just the `# {name}` heading.
 */
export function archiveToMarkdown(name: string, payload: unknown): string {
  const lines: string[] = [`# ${name}`, ""];

  const root = asRecord(payload);
  if (!root) return lines.join("\n");

  const session = asRecord(root.session);
  const title = typeof session?.title === "string" ? session.title : null;
  const messageCount =
    typeof root.message_count === "number" ? root.message_count : null;
  const meta: string[] = [];
  if (title) meta.push(title);
  if (messageCount != null) meta.push(`${messageCount} mensajes`);
  if (meta.length > 0) lines.push(meta.join(" · "), "");

  const files = asArray(root.files);
  if (files.length > 0) {
    lines.push("## Archivos", "");
    for (const file of files) {
      const f = asRecord(file);
      if (!f || typeof f.filename !== "string") continue;
      const parts: string[] = [];
      if (typeof f.format === "string") parts.push(f.format);
      if (typeof f.row_count === "number") parts.push(`${f.row_count} filas`);
      lines.push(parts.length > 0 ? `- ${f.filename} (${parts.join(", ")})` : `- ${f.filename}`);
    }
    lines.push("");
  }

  const messages = asArray(root.messages);
  if (messages.length > 0) {
    lines.push("## Conversación", "");
    for (const rawMessage of messages) {
      const message = asRecord(rawMessage);
      if (!message) continue;

      const isUser = message.role === "user";
      lines.push(isUser ? "### Usuario" : "### Asistente", "");

      const content =
        typeof message.content_text === "string" ? message.content_text : "";
      if (content.trim().length > 0) lines.push(content, "");

      const code = typeof message.code === "string" ? message.code : null;
      if (code && code.trim().length > 0) lines.push("```python", code, "```", "");

      lines.push(...artifactsToMarkdown(message.artifacts));
    }
  }

  return lines.join("\n");
}

/** Sanitize an archive name into a safe `.md` file name (strips path
 * separators and characters that break common filesystems). */
export function archiveMarkdownFilename(name: string): string {
  const base = (name ?? "")
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, " ")
    .replace(/\.+$/, "")
    .trim();
  return `${base || "analisis"}.md`;
}

/** Trigger a client-side download of a text file (mirrors
 * `DataFrameTable`'s data-URL download). */
export function downloadTextFile(text: string, filename: string): void {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
