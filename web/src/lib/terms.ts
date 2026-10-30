import termsEs from "../content/terms/terms.es.md?raw";
import termsEn from "../content/terms/terms.en.md?raw";

/**
 * The terms of use text, as the page reads it (terms-of-use S1/D3).
 *
 * The two markdown files under `content/terms` are the single source: this
 * module parses them instead of keeping a second copy in JSX, so the document
 * in the repository and the one a person reads on screen cannot disagree. The
 * server cross-checks the version printed here against the one the register
 * route enforces (D3), and the form sends `TERMS_VERSION` so the account
 * records which text was accepted (D5).
 */

export type TermsLanguage = "es" | "en";

export type TermsBlock =
  | { kind: "title"; text: string }
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "bullets"; items: string[] };

export interface TermsDocument {
  version: string;
  updated: string;
  blocks: TermsBlock[];
}

// "Versión:" (Spanish) and "Version:" (English) share one pattern. The metadata
// lines are shown in the page header, never as body text.
const VERSION_LINE = /^Versi[oó]n:\s*(\S+)$/;
const UPDATED_LINE = /^(?:Última actualización|Last updated):\s*(.+)$/;
const TITLE_LINE = /^#\s+(.+)$/;
const HEADING_LINE = /^##\s+(.+)$/;
const BULLET_LINE = /^-\s+(.+)$/;

/**
 * Turn one markdown document into the blocks the page renders.
 *
 * The supported subset is deliberately small -- title, section headings,
 * paragraphs and bullet lists -- because that is all a legal text needs and
 * every extra construct is code that has to be tested: no dependency, no HTML
 * injection, no parser to keep patching.
 */
export function parseTerms(source: string): TermsDocument {
  let version = "";
  let updated = "";
  const blocks: TermsBlock[] = [];
  let bullets: string[] = [];

  const flushBullets = () => {
    if (bullets.length === 0) return;
    blocks.push({ kind: "bullets", items: bullets });
    bullets = [];
  };

  for (const rawLine of source.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;

    const versionMatch = VERSION_LINE.exec(line);
    if (versionMatch) {
      version = versionMatch[1];
      continue;
    }

    const updatedMatch = UPDATED_LINE.exec(line);
    if (updatedMatch) {
      updated = updatedMatch[1];
      continue;
    }

    const bulletMatch = BULLET_LINE.exec(line);
    if (bulletMatch) {
      bullets.push(bulletMatch[1]);
      continue;
    }
    flushBullets();

    const titleMatch = TITLE_LINE.exec(line);
    if (titleMatch) {
      blocks.push({ kind: "title", text: titleMatch[1] });
      continue;
    }

    const headingMatch = HEADING_LINE.exec(line);
    if (headingMatch) {
      blocks.push({ kind: "heading", text: headingMatch[1] });
      continue;
    }

    blocks.push({ kind: "paragraph", text: line });
  }
  flushBullets();

  return { version, updated, blocks };
}

export const TERMS: Record<TermsLanguage, TermsDocument> = {
  es: parseTerms(termsEs),
  en: parseTerms(termsEn),
};

/**
 * The version the register form sends: the one the text declares (D3), so a
 * person cannot accept a text and have a different version recorded.
 */
export const TERMS_VERSION = TERMS.es.version;
