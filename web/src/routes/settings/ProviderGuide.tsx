// Inline step-by-step provider setup guide (PD2: inline copy + direct link).
//
// The copy is maintained here, keyed by guideId (the provider id). Each guide
// owns its own optional setupUrl so providers without a curated catalog
// (Ollama, LM Studio) still render their guide. An unknown id renders nothing,
// so callers can pass a catalog guideId without defending it.

import { GROQ_SETUP_URL, OPENROUTER_SETUP_URL } from "./recommended";

interface GuideContent {
  title: string;
  steps: string[];
  linkLabel: string;
  setupUrl?: string;
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
    setupUrl: OPENROUTER_SETUP_URL,
  },
  groq: {
    title: "Cómo configurar Groq",
    steps: [
      "Crea una cuenta en la consola de Groq (es gratis).",
      "Genera una clave de API desde la página de claves.",
      "Elige uno de los modelos recomendados; Groq cobra por uso (sin plan gratuito en el catálogo).",
      "Pega la clave en Datara. Se guarda en el servidor y nunca se comparte con el navegador.",
    ],
    linkLabel: "Abrir consola de Groq",
    setupUrl: GROQ_SETUP_URL,
  },
  ollama: {
    title: "Cómo configurar Ollama",
    steps: [
      "Instala Ollama en tu máquina.",
      "Inicia el servidor local (Ollama lo levanta al abrir la app o con «ollama serve»).",
      "Descarga un modelo, por ejemplo «ollama pull llama3.2».",
      "No hace falta clave de API: Datara se conecta al servidor local que ya tenés corriendo.",
    ],
    linkLabel: "Descargar Ollama",
    setupUrl: "https://ollama.com/download",
  },
  lmstudio: {
    title: "Cómo configurar LM Studio",
    steps: [
      "Instala LM Studio en tu máquina.",
      "Descarga un modelo desde la app y arráncalo en modo servidor local.",
      "Asegurate de que el servidor OpenAI-compatible esté escuchando en el puerto configurado.",
      "No hace falta clave de API: Datara se conecta al servidor local que ya tenés corriendo.",
    ],
    linkLabel: "Abrir LM Studio",
    setupUrl: "https://lmstudio.ai/",
  },
  custom: {
    title: "Cómo configurar un proveedor compatible",
    steps: [
      "Usa cualquier servidor compatible con la API de OpenAI.",
      "Ingresa la URL base que termina en /v1 (por ejemplo, https://mi-servidor/v1).",
      "Si el servidor exige autenticación, pega su clave de API; si no, dejala vacía.",
      "Escribe el identificador del modelo que expone tu servidor.",
    ],
    linkLabel: "",
  },
};

interface ProviderGuideProps {
  guideId: string;
}

export default function ProviderGuide({ guideId }: ProviderGuideProps) {
  const guide = GUIDES[guideId];
  if (!guide) return null;

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
      {guide.setupUrl && (
        <a
          href={guide.setupUrl}
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
