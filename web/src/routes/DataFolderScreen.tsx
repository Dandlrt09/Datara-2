import { useState } from "react";
import { ApiError } from "../lib/api";
import { useChooseDataFolder } from "../queries/useDataFolder";

interface DataFolderScreenProps {
  /** The folder the server would use right now (`GET path`). */
  currentPath: string;
  /** The recommended folder, the OS default (`GET default_path`). */
  defaultPath: string;
  /** Called when the analyst carries on after a successful decision. */
  onContinue?: () => void;
}

/** Backend rejection code -> the line the analyst reads.
 *
 * These codes belong to this screen, so the mapping lives here and not in the
 * shared provider-setup hook. A code the taxonomy does not know falls back to
 * the server's own Spanish message.
 */
const ERROR_MESSAGES: Record<string, string> = {
  invalid_path:
    "La ruta tiene que ser absoluta. Escribe una ruta completa, por ejemplo /home/usuario/datos.",
  path_not_writable: "No se puede escribir en esa carpeta. Elige otra ruta.",
  already_decided: "La carpeta de datos ya fue decidida en este equipo.",
};

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.body as
      | { detail?: { code?: string; message?: string } }
      | undefined;
    const code = detail?.detail?.code;
    if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code];
    if (detail?.detail?.message) return detail.detail.message;
  }
  return "No se pudo guardar la carpeta. Prueba de nuevo.";
}

/**
 * The first-run decision of *where the data lives* (enfoque A: pointer +
 * restart). It runs before any account exists, so it never needs a session.
 *
 * The choice is applied at the next boot, not here: this screen says so
 * instead of faking a `window.location.reload()`, which reloads the SPA but
 * does not re-open the store.
 */
export default function DataFolderScreen({
  currentPath,
  defaultPath,
  onContinue,
}: DataFolderScreenProps) {
  const [typed, setTyped] = useState(currentPath);
  const choose = useChooseDataFolder();
  const [decision, setDecision] = useState<{
    path: string;
    syncedClient: string | null;
  } | null>(null);

  const submit = async (path: string) => {
    try {
      const result = await choose.mutateAsync(path);
      setDecision({ path: result.path, syncedClient: result.synced_client });
    } catch {
      // Rendered from choose.error below.
    }
  };

  if (decision) {
    return (
      <div style={{ maxWidth: 560, margin: "80px auto", padding: 24 }}>
        <h1>Carpeta de datos elegida</h1>
        <p role="status">
          Guardamos <strong>{decision.path}</strong>. Cierra y vuelve a abrir
          Datara para usar la carpeta nueva.
        </p>
        {decision.syncedClient && (
          <p
            role="alert"
            style={{
              background: "#fff8f7",
              border: "1px solid #f2b8b5",
              color: "#c62828",
              padding: 12,
              borderRadius: 6,
            }}
          >
            Aviso: la carpeta que elegiste la sincroniza {decision.syncedClient}.
            Ese cliente puede copiar la base de Datara mientras la escribimos y
            replicar a la nube los datasets que subas. Puedes continuar igual:
            solo tenlo en cuenta.
          </p>
        )}
        <button type="button" onClick={onContinue} style={{ padding: 10 }}>
          Continuar
        </button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 560, margin: "80px auto", padding: 24 }}>
      <h1>¿Dónde guardamos tus datos?</h1>
      <p>
        Ahí viven la base de Datara y los datasets que subas. Elige una carpeta
        de este equipo.
      </p>
      <p>
        Carpeta actual: <strong>{currentPath}</strong>
      </p>
      <p>
        Carpeta recomendada: <strong>{defaultPath}</strong>
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit(typed);
        }}
      >
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="data-folder-path" style={{ display: "block", marginBottom: 4 }}>
            Carpeta de datos
          </label>
          <input
            id="data-folder-path"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder="/home/usuario/datos"
            style={{ width: "100%", padding: 8 }}
          />
        </div>
        {choose.error != null && (
          <p role="alert" style={{ color: "red" }}>
            {errorMessage(choose.error)}
          </p>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          <button type="submit" disabled={choose.isPending} style={{ padding: 10 }}>
            Usar esta carpeta
          </button>
          <button
            type="button"
            disabled={choose.isPending}
            onClick={() => void submit(defaultPath)}
            style={{ padding: 10 }}
          >
            Usar la carpeta recomendada
          </button>
        </div>
      </form>
    </div>
  );
}
