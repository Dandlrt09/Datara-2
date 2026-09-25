import { useEffect, useState } from "react";
import { ErrorCard } from "./ErrorCard";
import { useSelectFileSheet, type SheetSelectResult } from "../queries/useFiles";

export interface SheetPickerProps {
  /** The upload the picker re-profiles. */
  fileId: number;
  /** All sheet names in the workbook (length > 1 triggers the warning). */
  sheets: string[];
  /** The currently active sheet, if known. */
  currentSheet?: string | null;
  /** Called after a successful switch so the caller can dismiss the picker. */
  onSelected?: (result: SheetSelectResult) => void;
}

/**
 * Warning notice + sheet selector for a multi-sheet XLSX file.
 *
 * The upload path profiles the first sheet and says nothing; this surfaces
 * that there are more sheets and lets the user re-profile another one in
 * place (no re-upload). Built on ErrorCard's warning variant so it shares
 * the existing visual family (Decision D6).
 */
export function SheetPicker({
  fileId,
  sheets,
  currentSheet,
  onSelected,
}: SheetPickerProps) {
  const [selected, setSelected] = useState(currentSheet ?? sheets[0] ?? "");
  const selectSheet = useSelectFileSheet();

  // Keep the selection in sync when the active sheet or list changes (e.g.
  // after a switch invalidates the file query).
  useEffect(() => {
    setSelected(currentSheet ?? sheets[0] ?? "");
  }, [currentSheet, sheets]);

  const pending = selectSheet.isPending;

  const handleApply = async () => {
    if (!selected) return;
    try {
      const result = await selectSheet.mutateAsync({ fileId, sheetName: selected });
      onSelected?.(result);
    } catch {
      // The card re-renders with the mutation error below.
    }
  };

  const message = selectSheet.isError
    ? ((selectSheet.error as Error)?.message ?? "Failed to switch sheet.")
    : "Datara analyzed the first sheet. Choose which sheet to analyze.";

  return (
    <ErrorCard
      variant="warning"
      title={`This workbook has ${sheets.length} sheets`}
      message={message}
    >
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <label htmlFor={`sheet-picker-${fileId}`} style={{ color: "#555" }}>
          Sheet:
        </label>
        <select
          id={`sheet-picker-${fileId}`}
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={pending}
          style={{ padding: "6px 12px", minWidth: 160 }}
        >
          {sheets.map((sheet) => (
            <option key={sheet} value={sheet}>
              {sheet}
            </option>
          ))}
        </select>
        <button onClick={handleApply} disabled={pending || !selected}>
          {pending ? "Applying…" : "Analyze this sheet"}
        </button>
      </div>
    </ErrorCard>
  );
}
