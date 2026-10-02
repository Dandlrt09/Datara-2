import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SaveAnalysisDialog } from "../components/SaveAnalysisDialog";

describe("SaveAnalysisDialog", () => {
  it("renders nothing when closed", () => {
    render(
      <SaveAnalysisDialog
        open={false}
        defaultName="Ventas"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("prefills the name input with defaultName and focuses it", () => {
    render(
      <SaveAnalysisDialog
        open
        defaultName="Ventas Q3"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const input = screen.getByLabelText("Nombre del análisis") as HTMLInputElement;
    expect(input.value).toBe("Ventas Q3");
    // Default focus lands on the input so typing starts immediately.
    expect(document.activeElement).toBe(input);
  });

  it("disables confirm for an empty or whitespace-only name", () => {
    render(
      <SaveAnalysisDialog
        open
        defaultName=""
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const confirm = screen.getByRole("button", { name: "Guardar" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Nombre del análisis"), {
      target: { value: "   " },
    });
    expect(confirm.disabled).toBe(true);
  });

  it("trims the name before calling onConfirm", () => {
    const onConfirm = vi.fn();
    render(
      <SaveAnalysisDialog
        open
        defaultName=""
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Nombre del análisis"), {
      target: { value: "  Ventas Q3  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(onConfirm).toHaveBeenCalledWith("Ventas Q3");
  });

  it("invokes onCancel on Escape without confirming", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <SaveAnalysisDialog
        open
        defaultName="Ventas"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("ignores Escape while pending", () => {
    const onCancel = vi.fn();
    render(
      <SaveAnalysisDialog
        open
        defaultName="Ventas"
        onConfirm={vi.fn()}
        onCancel={onCancel}
        pending
      />,
    );
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("invokes onCancel on Cancel without confirming", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <SaveAnalysisDialog
        open
        defaultName="Ventas"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("disables both actions while pending", () => {
    render(
      <SaveAnalysisDialog
        open
        defaultName="Ventas"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        pending
      />,
    );
    expect(
      (screen.getByRole("button", { name: "Cancelar" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Guardando…" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("renders the error copy inside the dialog", () => {
    render(
      <SaveAnalysisDialog
        open
        defaultName="Ventas"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        error="No se pudo guardar el análisis. Inténtalo de nuevo."
      />,
    );
    expect(
      screen.getByRole("alert").textContent,
    ).toContain("No se pudo guardar el análisis. Inténtalo de nuevo.");
  });

  it("caps the name input at 200 characters", () => {
    render(
      <SaveAnalysisDialog
        open
        defaultName="Ventas"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(
      screen.getByLabelText("Nombre del análisis").getAttribute("maxLength"),
    ).toBe("200");
  });
});
