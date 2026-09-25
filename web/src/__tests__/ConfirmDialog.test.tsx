import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { ConfirmDialog } from "../components/ConfirmDialog";

function Harness({
  onConfirm,
  onCancel,
  pending = false,
}: {
  onConfirm: () => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open dialog</button>
      <ConfirmDialog
        open={open}
        title="Delete file"
        message={'Delete "sales.csv"? This cannot be undone.'}
        confirmLabel="Delete file"
        cancelLabel="Cancel"
        onConfirm={onConfirm}
        onCancel={() => {
          onCancel();
          setOpen(false);
        }}
        pending={pending}
      />
    </div>
  );
}

function openDialog() {
  const trigger = screen.getByRole("button", { name: "Open dialog" });
  // fireEvent.click does not focus in jsdom; focus explicitly so the focus
  // trap can save and later restore the trigger.
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}

describe("ConfirmDialog", () => {
  it("renders an accessible modal dialog naming the action and file", () => {
    renderWithProviders(<Harness onConfirm={vi.fn()} onCancel={vi.fn()} />);

    openDialog();

    const dialog = screen.getByRole("dialog", { name: "Delete file" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(screen.getByText('Delete "sales.csv"? This cannot be undone.')).toBeTruthy();
  });

  it("focuses Cancel by default so Enter is safe", () => {
    renderWithProviders(<Harness onConfirm={vi.fn()} onCancel={vi.fn()} />);

    openDialog();

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
  });

  it("Escape cancels the dialog", () => {
    const onCancel = vi.fn();
    renderWithProviders(<Harness onConfirm={vi.fn()} onCancel={onCancel} />);

    openDialog();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Cancel cancels the dialog", () => {
    const onCancel = vi.fn();
    renderWithProviders(<Harness onConfirm={vi.fn()} onCancel={onCancel} />);

    openDialog();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("confirm fires onConfirm", () => {
    const onConfirm = vi.fn();
    renderWithProviders(<Harness onConfirm={onConfirm} onCancel={vi.fn()} />);

    openDialog();
    fireEvent.click(screen.getByRole("button", { name: "Delete file" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("restores focus to the trigger on close", () => {
    renderWithProviders(<Harness onConfirm={vi.fn()} onCancel={vi.fn()} />);

    const trigger = openDialog();
    expect(document.activeElement).not.toBe(trigger);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(document.activeElement).toBe(trigger);
  });

  it("disables both actions while pending", () => {
    renderWithProviders(<Harness onConfirm={vi.fn()} onCancel={vi.fn()} pending />);

    openDialog();

    const cancel = screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement;
    const confirm = screen.getByRole("button", { name: "Delete file" }) as HTMLButtonElement;
    expect(cancel.disabled).toBe(true);
    expect(confirm.disabled).toBe(true);
  });

  it("renders nothing when closed", () => {
    renderWithProviders(<Harness onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
