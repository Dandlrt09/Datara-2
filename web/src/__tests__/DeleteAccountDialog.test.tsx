import { describe, it, expect, vi, beforeEach } from "vitest";
import { useState } from "react";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import {
  DeleteAccountDialog,
  DELETE_CONFIRMATION_WORD,
  DELETION_SCHEDULED_NOTICE,
} from "../components/DeleteAccountDialog";
import { ApiError } from "../lib/api";

const { authState } = vi.hoisted(() => ({
  authState: { pending: false, mutate: vi.fn() },
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => ({ data: undefined, isLoading: false, error: null }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useChangePassword: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn() }),
  useRequestAccountDeletion: () => ({
    mutate: authState.mutate,
    isPending: authState.pending,
    reset: vi.fn(),
  }),
  useCancelAccountDeletion: () => ({ mutate: vi.fn(), isPending: false }),
}));

/** Mirrors how `ProfileView` owns the dialog: on success it closes and the
 * parent redirects. Kept here so the dialog's success contract is observable. */
function Harness() {
  const [open, setOpen] = useState(true);
  const [done, setDone] = useState(false);
  return (
    <div>
      {done && <p role="status">{DELETION_SCHEDULED_NOTICE}</p>}
      <DeleteAccountDialog
        open={open}
        onSuccess={() => {
          setOpen(false);
          setDone(true);
        }}
        onCancel={() => setOpen(false)}
      />
    </div>
  );
}

function fillAndSubmit(word = DELETE_CONFIRMATION_WORD, password = "clave-1234") {
  fireEvent.change(screen.getByLabelText(/\S.*ELIMINAR.*confirmar/), {
    target: { value: word },
  });
  fireEvent.change(screen.getByLabelText("Contraseña actual"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole("button", { name: "Eliminar mi cuenta" }));
}

describe("DeleteAccountDialog", () => {
  beforeEach(() => {
    authState.pending = false;
    authState.mutate.mockReset();
  });

  it("renders the confirmation and password fields, focusing Cancel", () => {
    renderWithProviders(<Harness />);

    expect(screen.getByRole("dialog", { name: "Eliminar cuenta" })).toBeTruthy();
    expect(
      screen.getByLabelText(/ELIMINAR.*confirmar/).getAttribute("type"),
    ).toBe("text");
    expect(screen.getByLabelText("Contraseña actual").getAttribute("type")).toBe(
      "password",
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Cancelar" }),
    );
  });

  it("warns that the stored API key and data are deleted", () => {
    renderWithProviders(<Harness />);

    expect(screen.getByText(/API key guardada/)).toBeTruthy();
  });

  it("sends the word and the password to the mutation", () => {
    authState.mutate.mockImplementation(() => {});
    renderWithProviders(<Harness />);

    fillAndSubmit("ELIMINAR", "clave-1234");

    expect(authState.mutate).toHaveBeenCalledWith(
      { confirmation: "ELIMINAR", current_password: "clave-1234" },
      expect.any(Object),
    );
  });

  it("maps 401 to the wrong-password copy inside the dialog", () => {
    authState.mutate.mockImplementation((_vars, options) =>
      options.onError(new ApiError(401, { detail: "Current password is incorrect" })),
    );
    renderWithProviders(<Harness />);

    fillAndSubmit();

    expect(screen.getByRole("alert").textContent).toBe(
      "La contraseña no es correcta.",
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("maps 422 to the confirmation-word copy inside the dialog", () => {
    authState.mutate.mockImplementation((_vars, options) =>
      options.onError(new ApiError(422, { detail: "Type ELIMINAR to confirm" })),
    );
    renderWithProviders(<Harness />);

    fillAndSubmit("eliminar");

    expect(screen.getByRole("alert").textContent).toBe(
      "Escribí ELIMINAR para confirmar.",
    );
  });

  it("maps any other failure to the generic copy inside the dialog", () => {
    authState.mutate.mockImplementation((_vars, options) =>
      options.onError(new ApiError(500, {})),
    );
    renderWithProviders(<Harness />);

    fillAndSubmit();

    expect(screen.getByRole("alert").textContent).toBe(
      "No se pudo programar el borrado. Vuelve a intentarlo.",
    );
  });

  it("closes and reports success after the request succeeds", async () => {
    authState.mutate.mockImplementation((_vars, options) => options.onSuccess());
    renderWithProviders(<Harness />);

    fillAndSubmit();

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("status").textContent).toBe(DELETION_SCHEDULED_NOTICE);
  });

  it("closes on Escape without sending the mutation", () => {
    renderWithProviders(<Harness />);

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(authState.mutate).not.toHaveBeenCalled();
  });

  it("closes on Cancel without sending the mutation", () => {
    renderWithProviders(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

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
      (
        screen.getByRole("button", {
          name: "Eliminando…",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
});
