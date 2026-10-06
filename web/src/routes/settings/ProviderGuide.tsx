// Inline step-by-step provider setup guide (PD2: inline copy + direct link).
//
// The copy is maintained here, keyed by guideId. An unknown id renders
// nothing so callers can pass a catalog guideId without defending it.

import { RECOMMENDED_MODELS } from "./recommended";

interface GuideContent {
  title: string;
  steps: string[];
  linkLabel: string;
}

const GUIDES: Record<string, GuideContent> = {
  openrouter: {
    title: "Cómo configurar OpenRouter",
    steps: [
      "Crea una cuenta en OpenRouter (es gratis).",
      "Genera una clave de API desde tu panel de claves.",
      "Carga créditos si vas a usar modelos de pago; los modelos gratuitos no requieren saldo.",
      "Pega la clave en Datara. Se guarda en el servidor y nunca se comparte con el navegador.",
    ],
    linkLabel: "Abrir OpenRouter",
  },
};

interface ProviderGuideProps {
  guideId: string;
}

export default function ProviderGuide({ guideId }: ProviderGuideProps) {
  const guide = GUIDES[guideId];
  if (!guide) return null;

  const setupUrl = RECOMMENDED_MODELS.find((m) => m.guideId === guideId)?.setupUrl;

  return (
    <section style={{ marginBottom: 24, padding: 16, border: "1px solid #ddd", borderRadius: 4 }}>
      <h2 style={{ fontSize: "1.1em", marginTop: 0 }}>{guide.title}</h2>
      <ol style={{ margin: "0 0 12px", paddingLeft: 20 }}>
        {guide.steps.map((step, index) => (
          <li key={index} style={{ marginBottom: 4 }}>
            {step}
          </li>
        ))}
      </ol>
      {setupUrl && (
        <a
          href={setupUrl}
          target="_blank"
          rel="noopener noreferrer"
          style={{ display: "inline-block", padding: "8px 16px", backgroundColor: "#007acc", color: "white", borderRadius: 4, textDecoration: "none" }}
        >
          {guide.linkLabel}
        </a>
      )}
    </section>
  );
}
