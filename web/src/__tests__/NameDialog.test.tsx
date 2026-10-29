import { describe, it, expect, vi, beforeEach } from "vitest";
import { useState } from "react";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import {
  NameDialog,
  MAX_NAME_LENGTH,
  NAME_UPDATED_NOTICE,
} from "../components/NameDialog";
import { ApiError } from "../lib/api";

const { authState } = vi.hoisted(() => ({
  authState: { pending: false, mutate: vi.fn() },
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => ({ data: undefined, isLoading: false, error: null }),
  useUpdateName: () => ({
    mutate: authState.mutate,
    isPending: authState.pending,
  }),
}));

/** Mirrors ProfileView owning the dialog: success closes it and shows the notice. */
function Harness({ initialName = null }: { initialName?: string | null }) {
  const [open, setOpen] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Abrir
      </button>
      {notice && <p role="status">{notice}</p>}
      <NameDialog
        open={open}
        initialName={initialName}
        onSuccess={() => {
          setOpen(false);
          setNotice(NAME_UPDATED_NOTICE);
        }}
        onCancel={() => setOpen(false)}
      />
    </div>
  );
}

function submitName(value: string) {
  fireEvent.change(screen.getByLabelText("Nombre"), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
}

// The mutation callbacks are the second argument of react-query's `mutate`.
interface MutateOptions {
  onSuccess: () => void;
  onError: (error: unknown) => void;
}

describe("NameDialog", () => {
  beforeEach(() => {
    authState.pending = false;
    authState.mutate.mockReset();
  });

  it("prefills the current name and focuses Cancel by default", () => {
    renderWithProviders(<Harness initialName="Daniel" />);

    expect(screen.getByRole("dialog", { name: "Editar nombre" })).toBeTruthy();
    expect((screen.getByLabelText("Nombre") as HTMLInputElement).value).toBe(
      "Daniel",
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Cancelar" }),
    );
  });

  it("leaves the input empty when the user never chose a name", () => {
    renderWithProviders(<Harness initialName={null} />);

    expect((screen.getByLabelText("Nombre") as HTMLInputElement).value).toBe("");
  });

  it("sends the typed name to the mutation", () => {
    authState.mutate.mockImplementation(() => {});
    renderWithProviders(<Harness />);

    submitName("Daniel Del Rio");

    expect(authState.mutate).toHaveBeenCalledWith(
      { name: "Daniel Del Rio" },
      expect.any(Object),
    );
  });

  it("refuses a blank name and warns instead of submitting", () => {
    // D3 (rewritten on 29/10): leaving the field empty no longer clears the
    // name, so the dialog must not send anything at all.
    authState.mutate.mockImplementation(() => {});
    renderWithProviders(<Harness initialName="Daniel" />);

    submitName("   ");

    expect(screen.getByRole("alert").textContent).toBe(
      "El nombre no puede quedar vacío.",
    );
    expect(authState.mutate).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("caps the input at the documented limit", () => {
    renderWithProviders(<Harness />);

    const input = screen.getByLabelText("Nombre") as HTMLInputElement;

    expect(input.getAttribute("maxlength")).toBe(String(MAX_NAME_LENGTH));
    expect(screen.getByText(`Hasta ${MAX_NAME_LENGTH} caracteres.`)).toBeTruthy();
  });

  it("closes the dialog and shows the notice on success", async () => {
    authState.mutate.mockImplementation((_vars: unknown, options: MutateOptions) =>
      options.onSuccess(),
    );
    renderWithProviders(<Harness />);

    submitName("Daniel");

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("status").textContent).toBe(NAME_UPDATED_NOTICE);
  });

  it("maps 422 to the length copy and keeps the dialog open", () => {
    authState.mutate.mockImplementation((_vars: unknown, options: MutateOptions) =>
      options.onError(
        new ApiError(422, {
          detail: `Name must be at most ${MAX_NAME_LENGTH} characters`,
        }),
      ),
    );
    renderWithProviders(<Harness />);

    submitName("x".repeat(MAX_NAME_LENGTH + 1));

    expect(screen.getByRole("alert").textContent).toBe(
      `El nombre no puede tener más de ${MAX_NAME_LENGTH} caracteres.`,
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("maps any other failure to the generic copy", () => {
    authState.mutate.mockImplementation((_vars: unknown, options: MutateOptions) =>
      options.onError(new ApiError(500, {})),
    );
    renderWithProviders(<Harness />);

    submitName("Daniel");

    expect(screen.getByRole("alert").textContent).toBe(
      "No se pudo guardar el nombre. Vuelve a intentarlo.",
    );
  });

  it("closes on Cancel without sending the mutation", () => {
    renderWithProviders(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(authState.mutate).not.toHaveBeenCalled();
  });

  it("closes on Escape without sending the mutation", () => {
    renderWithProviders(<Harness />);

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(authState.mutate).not.toHaveBeenCalled();
  });

  it("disables both actions while pending", () => {
    authState.pending = true;
    renderWithProviders(<Harness />);

    expect(
      (screen.getByRole("button", { name: "Cancelar" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Guardando…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
