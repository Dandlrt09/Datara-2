import { useState } from "react";
import { Link } from "react-router-dom";
import { TERMS, type TermsBlock, type TermsLanguage } from "../lib/terms";

const NEXT_LANGUAGE: Record<TermsLanguage, TermsLanguage> = { es: "en", en: "es" };
const LANGUAGE_NAME: Record<TermsLanguage, string> = { es: "Español", en: "English" };
const VERSION_LABEL: Record<TermsLanguage, string> = { es: "Versión", en: "Version" };
const BACK_LABEL: Record<TermsLanguage, string> = {
  es: "Volver al alta",
  en: "Back to sign up",
};

/** One parsed block, rendered as the element it stands for (D6). */
function Block({ block }: { block: TermsBlock }) {
  if (block.kind === "bullets") {
    return (
      <ul style={{ paddingLeft: 20, lineHeight: 1.6 }}>
        {block.items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    );
  }
  if (block.kind === "title") return <h1>{block.text}</h1>;
  if (block.kind === "heading") return <h2>{block.text}</h2>;
  return <p style={{ lineHeight: 1.6 }}>{block.text}</p>;
}

/**
 * The terms of use, readable without an account (S1).
 *
 * The page is reachable from the signup form, which is where someone needs to
 * read it before accepting, and it keeps both languages in one screen: the
 * toggle switches the whole document rather than showing halves of each.
 */
export default function TermsScreen() {
  const [language, setLanguage] = useState<TermsLanguage>("es");
  const document = TERMS[language];

  return (
    <div style={{ maxWidth: 720, margin: "40px auto", padding: 24 }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <p style={{ fontSize: 13, color: "#5f6368", margin: 0 }}>
          {`${VERSION_LABEL[language]} ${document.version} · ${document.updated}`}
        </p>
        <button
          type="button"
          onClick={() => setLanguage(NEXT_LANGUAGE[language])}
          style={{
            padding: "4px 10px",
            border: "1px solid #dadce0",
            borderRadius: 4,
            background: "none",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          {LANGUAGE_NAME[NEXT_LANGUAGE[language]]}
        </button>
      </header>

      {document.blocks.map((block, index) => (
        <Block key={index} block={block} />
      ))}

      <p style={{ marginTop: 32 }}>
        <Link to="/register">{BACK_LABEL[language]}</Link>
      </p>
    </div>
  );
}
