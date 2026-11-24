/* F5 (S5): the crossing panel of the chat screen.
 *
 * The analyst picks two of the session's files, asks Datara to propose the
 * keys and the join kind, confirms (or adjusts) the recipe, and reads how the
 * merge ended. One crossing stays active per session; the server owns the
 * recipe and its imbalance, this panel only shows them.
 *
 * All data comes from `useCrossings` hooks; the panel is a thin, presentational
 * consumer so its behavior is testable through the DOM.
 */
import { useState } from "react";
import { formatNumber, usePreferences } from "../lib/preferences";
import {
  useConfirmCrossing,
  useCrossing,
  useCrossingFiles,
  useCrossingProfile,
  useDeleteCrossing,
  useProposeCrossing,
  type JoinKind,
} from "../queries/useCrossings";

/** Join kinds in product language; the values are the wire values. */
const JOIN_KINDS: { value: JoinKind; label: string }[] = [
  { value: "inner", label: "Solo las coincidencias" },
  { value: "left", label: "Todas las filas de la izquierda" },
  { value: "right", label: "Todas las filas de la derecha" },
  { value: "outer", label: "Todas las filas de ambos" },
];

/** One refusal copy for every failed crossing request (S5-6). */
const REQUEST_ERROR = "No se pudo guardar el cruce. Prueba de nuevo.";

const NOT_FOUND =
  "El modelo no encontró una columna para cruzar. Elige las columnas a mano.";
const UNAVAILABLE =
  "No se pudo consultar al modelo. Prueba de nuevo o elige las columnas a mano.";

/** S7: the short in-panel guide, one entry per step. Exact product copy
 * (neutral Spanish, tuteo). */
const GUIDE_STEPS = [
  "Elige el archivo izquierdo y el archivo derecho: son los dos que quieres cruzar.",
  "Pulsa «Proponer cruce» y Datara propone por qué columna cruzarlos. Puedes cambiar la columna cuando quieras.",
  "Elige el tipo de cruce: «Solo las coincidencias» deja únicamente las filas que existen en los dos archivos, y «Todas las filas…» conserva las de uno o de los dos lados.",
  "Pulsa «Confirmar cruce»: Datara te dice cuántas filas quedaron en el resultado y cuántas afuera de cada lado. Desde ahí puedes preguntar sobre el cruce.",
];

const GUIDE_NOTE =
  "Siempre hay un cruce activo por sesión: puedes cambiarlo o quitarlo cuando quieras.";

/** Column names of a profile payload, defensively read. */
function columnNames(profile: { schema?: { columns?: { name: string }[] } } | undefined) {
  return (profile?.schema?.columns ?? []).map((column) => column.name);
}

export default function CrossingPanel({
  sessionId,
}: {
  sessionId: string | null;
}) {
  const { numberFormat } = usePreferences();

  const filesQuery = useCrossingFiles(sessionId);
  const crossingQuery = useCrossing(sessionId);

  const [open, setOpen] = useState(false);
  // S7: the inline help is closed until the analyst asks for it.
  const [guideOpen, setGuideOpen] = useState(false);
  const [leftFileId, setLeftFileId] = useState<number | null>(null);
  const [rightFileId, setRightFileId] = useState<number | null>(null);
  const [leftKey, setLeftKey] = useState("");
  const [rightKey, setRightKey] = useState("");
  const [how, setHow] = useState<JoinKind>("inner");
  const [proposalLine, setProposalLine] = useState<string | null>(null);
  const [proposalReason, setProposalReason] = useState<string | null>(null);
  const [imbalance, setImbalance] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const leftProfile = useCrossingProfile(leftFileId);
  const rightProfile = useCrossingProfile(rightFileId);

  const propose = useProposeCrossing(sessionId);
  const confirm = useConfirmCrossing(sessionId);
  const remove = useDeleteCrossing(sessionId);

  const files = filesQuery.data ?? [];
  // Every hook above runs unconditionally; a session with fewer than two
  // datasets simply has nothing to cross.
  if (!sessionId || files.length < 2) return null;

  const active = crossingQuery.data?.crossing ?? null;
  const leftColumns = columnNames(leftProfile.data);
  const rightColumns = columnNames(rightProfile.data);
  const filesPicked = leftFileId !== null && rightFileId !== null;
  const keysPicked = filesPicked && !!leftKey && !!rightKey;

  const handlePropose = async () => {
    if (leftFileId === null || rightFileId === null) return;
    setError(null);
    setProposalLine(null);
    setProposalReason(null);
    try {
      const response = await propose.mutateAsync({
        left_file_id: leftFileId,
        right_file_id: rightFileId,
      });
      const proposal = response.proposal;
      if (proposal) {
        setLeftKey(proposal.left_key);
        setRightKey(proposal.right_key);
        setHow(proposal.how);
        setProposalLine(
          `El modelo propone cruzar por «${proposal.left_key}» = «${proposal.right_key}».`,
        );
        // The model's why is English server prose: secondary detail only.
        setProposalReason(proposal.reason);
      } else if (response.code === "proposal_not_found") {
        // Nothing usable came out: let the analyst pick the columns by hand.
        setLeftKey("");
        setRightKey("");
        setProposalLine(NOT_FOUND);
      } else {
        // proposal_unavailable, or an unknown code: offer a retry.
        setProposalLine(UNAVAILABLE);
      }
    } catch {
      setError(REQUEST_ERROR);
    }
  };

  const handleConfirm = async () => {
    if (leftFileId === null || rightFileId === null || !leftKey || !rightKey) {
      return;
    }
    setError(null);
    setImbalance(null);
    try {
      const confirmed = await confirm.mutateAsync({
        left_file_id: leftFileId,
        right_file_id: rightFileId,
        left_key: leftKey,
        right_key: rightKey,
        how,
      });
      const d = confirmed.diagnostics;
      setImbalance(
        `${formatNumber(d.result_rows, numberFormat)} filas en el resultado · ` +
          `${formatNumber(d.matched_rows, numberFormat)} coincidencias · ` +
          `${formatNumber(d.left_only_rows, numberFormat)} quedaron afuera de «${confirmed.left_filename}» · ` +
          `${formatNumber(d.right_only_rows, numberFormat)} quedaron afuera de «${confirmed.right_filename}».`,
      );
    } catch {
      setError(REQUEST_ERROR);
    }
  };

  const handleDelete = async () => {
    setError(null);
    try {
      await remove.mutateAsync();
    } catch {
      setError(REQUEST_ERROR);
    }
  };

  return (
    <div
      data-testid="crossing-panel"
      style={{ borderTop: "1px solid #ddd", padding: "8px 16px" }}
    >
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button type="button" onClick={() => setOpen((value) => !value)}>
          Cruzar archivos
        </button>
        <button
          type="button"
          onClick={() => setGuideOpen((value) => !value)}
        >
          ¿Cómo funciona?
        </button>
      </div>

      {guideOpen && (
        <div
          style={{
            marginTop: 8,
            maxWidth: 640,
            background: "#f8f9fa",
            border: "1px solid #e0e0e0",
            borderRadius: 6,
            padding: "8px 12px",
          }}
        >
          <p style={{ margin: "0 0 8px", fontWeight: 600 }}>
            Cómo cruzar dos archivos
          </p>
          <ol
            style={{
              margin: 0,
              paddingLeft: 20,
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}
          >
            {GUIDE_STEPS.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <p style={{ margin: "8px 0", color: "#555" }}>{GUIDE_NOTE}</p>
          <button type="button" onClick={() => setGuideOpen(false)}>
            Cerrar
          </button>
        </div>
      )}

      {active && (
        <div style={{ marginTop: 8 }}>
          <p style={{ margin: 0 }}>
            {`Cruce activo: «${active.left_filename}» y «${active.right_filename}» por «${active.left_key}» = «${active.right_key}»`}
          </p>
          {/* The stored recipe carries no counts and they are never
              re-measured on load, so no numbers are shown here. */}
          <button type="button" onClick={handleDelete}>
            Quitar cruce
          </button>
        </div>
      )}

      {open && (
        <div
          style={{
            marginTop: 8,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            maxWidth: 640,
          }}
        >
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <label htmlFor="crossing-left-file">Archivo izquierdo</label>
            <select
              id="crossing-left-file"
              value={leftFileId ?? ""}
              onChange={(event) => {
                setLeftFileId(
                  event.target.value ? Number(event.target.value) : null,
                );
                setLeftKey("");
              }}
            >
              <option value="">Elige un archivo</option>
              {files.map((file) => (
                <option key={file.id} value={file.id}>
                  {file.filename}
                </option>
              ))}
            </select>

            <label htmlFor="crossing-right-file">Archivo derecho</label>
            <select
              id="crossing-right-file"
              value={rightFileId ?? ""}
              onChange={(event) => {
                setRightFileId(
                  event.target.value ? Number(event.target.value) : null,
                );
                setRightKey("");
              }}
            >
              <option value="">Elige un archivo</option>
              {files.map((file) => (
                <option key={file.id} value={file.id}>
                  {file.filename}
                </option>
              ))}
            </select>
          </div>

          <div>
            <button
              type="button"
              onClick={handlePropose}
              disabled={!filesPicked}
            >
              Proponer cruce
            </button>
          </div>

          {proposalLine && <p style={{ margin: 0 }}>{proposalLine}</p>}
          {proposalReason && (
            <p style={{ margin: 0, color: "#666", fontSize: "0.9em" }}>
              {proposalReason}
            </p>
          )}

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <label htmlFor="crossing-left-key">
              Columna del archivo izquierdo
            </label>
            <select
              id="crossing-left-key"
              value={leftKey}
              onChange={(event) => setLeftKey(event.target.value)}
            >
              <option value="">Elige una columna</option>
              {leftColumns.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>

            <label htmlFor="crossing-right-key">
              Columna del archivo derecho
            </label>
            <select
              id="crossing-right-key"
              value={rightKey}
              onChange={(event) => setRightKey(event.target.value)}
            >
              <option value="">Elige una columna</option>
              {rightColumns.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <label htmlFor="crossing-how">Tipo de cruce</label>
            <select
              id="crossing-how"
              value={how}
              onChange={(event) => setHow(event.target.value as JoinKind)}
            >
              {JOIN_KINDS.map((kind) => (
                <option key={kind.value} value={kind.value}>
                  {kind.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={!keysPicked}
            >
              Confirmar cruce
            </button>
          </div>

          {imbalance && (
            <p role="status" style={{ margin: 0 }}>
              {imbalance}
            </p>
          )}
          {error && (
            <p role="alert" style={{ margin: 0, color: "#c62828" }}>
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
