// Spanish user-facing copy for the provider setup wizard.
// Exact byte-exact strings from the spec table.

export const COPY = {
  // Step labels of the fused guided flow (provider -> credentials -> model).
  // The connection test and the confirmation are no longer steps: they are the
  // result of saving, which is what the user can actually observe.
  GUIDED_STEPS: ["Proveedor", "Credenciales", "Modelo", "Resultado"],

  // Provider step (shared by every screen since the fusion).
  PROVIDER_REQUIRED: "Selecciona un proveedor",
  // A stored provider that no shipped preset carries is offered, never
  // dropped: the label keeps the raw id visible so it can be recognized.
  LEGACY_PROVIDER_LABEL: (id: string) => `Otro (${id})`,
  LEGACY_PROVIDER_HINT:
    "Este proveedor quedó guardado por una versión anterior de Datara. Al guardar, revisá que la URL base sea la correcta.",

  // Honest save lifecycle copy: a successful PUT is not enough to claim
  // "Connected" — the probe has the last word.
  STATUS: {
    SAVED: "Ajustes guardados",
    CONNECTED: "Guardado · Conectado",
    UNVERIFIED: (detail: string) => `Guardado, pero falló la conexión: ${detail}`,
    SAVE_ERROR: (detail: string) => `No se pudieron guardar los ajustes: ${detail}`,
    SAVING: "Guardando...",
    CHECKING: "Comprobando...",
  },

  // Buttons
  BUTTONS: {
    PREVIOUS: "Anterior",
    NEXT: "Siguiente",
    FINISH: "Finalizar",
    EXIT: "Salir",
    RETRY: "Reintentar",
    SAVE: "Guardar",
    LOAD_MODELS: "Cargar modelos",
  },

  // Validation messages
  KEY_REQUIRED: "Introduce una clave de API para continuar.",
  BASE_URL_REQUIRED: "Introduce la URL base del proveedor.",
  SSRF_REJECTION:
    "La URL base debe usar HTTPS y apuntar a un host público. No se permiten direcciones locales ni privadas.",
  MODEL_LIST_FALLBACK:
    "No se pudo obtener la lista de modelos. Escribe el identificador del modelo manualmente.",
  MODEL_REQUIRED: "Selecciona un modelo o escribe su identificador.",
  MODEL_SEARCH_PLACEHOLDER: "Buscar modelo (nombre o id)...",
  MODEL_SEARCH_NO_RESULTS: "Sin resultados para",
  MODEL_NOT_ALLOWED: "Ese modelo no está permitido. Selecciona uno de la lista permitida.",

  // Provider-specific placeholder for the free-text / fallback model entry.
  // The generic value is the historical default and the OpenRouter fallback.
  MODEL_PLACEHOLDER_DEFAULT: "gpt-4o, llama3.2:latest, etc.",
  MODEL_PLACEHOLDERS: {
    openrouter: "gpt-4o, llama3.2:latest, etc.",
    ollama: "llama3.2, qwen2.5, etc.",
    lmstudio: "nombre-del-modelo",
    groq: "openai/gpt-oss-120b",
    custom: "gpt-4o, llama3.2:latest, etc.",
  } as Record<string, string>,

  // Keyless provider (Ollama / LM Studio) hint when the model fetch failed or
  // returned an empty list: the local server is the likely missing piece.
  MODEL_LOCAL_SERVER_HINT: (label: string) =>
    `¿«${label}» está corriendo en tu máquina?`,

  // Keyless provider (Ollama / LM Studio) credentials-step info block.
  KEYLESS_NO_KEY_REQUIRED: (label: string) => `«${label}» no requiere clave de API.`,
  KEYLESS_ENDPOINT_LABEL: "Endpoint que usará Datara:",
  KEYLESS_SERVER_HINT: (label: string) =>
    `Asegurate de tener «${label}» corriendo en tu máquina.`,
} as const;