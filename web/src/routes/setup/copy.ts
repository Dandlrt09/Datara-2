// Spanish user-facing copy for the provider setup wizard.
// Exact byte-exact strings from the spec table.

export const COPY = {
  // Step labels
  STEPS: ["Proveedor", "Credenciales", "Modelo", "Prueba de conexión", "Listo"],

  // Buttons
  BUTTONS: {
    PREVIOUS: "Anterior",
    NEXT: "Siguiente",
    FINISH: "Finalizar",
    EXIT: "Salir",
    RETRY: "Reintentar",
  },

  // Validation messages
  KEY_REQUIRED: "Introduce una clave de API para continuar.",
  BASE_URL_REQUIRED: "Introduce la URL base del proveedor.",
  SSRF_REJECTION:
    "La URL base debe usar HTTPS y apuntar a un host público. No se permiten direcciones locales ni privadas.",
  TEST_FAILED:
    "No se pudo conectar con el proveedor. Revisa la clave y la URL base, e inténtalo de nuevo.",
  MODEL_LIST_FALLBACK:
    "No se pudo obtener la lista de modelos. Escribe el identificador del modelo manualmente.",
  MODEL_REQUIRED: "Selecciona un modelo o escribe su identificador.",
  DONE_CONFIRMATION: "Configuración guardada correctamente.",
} as const;