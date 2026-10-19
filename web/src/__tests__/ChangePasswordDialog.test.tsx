import { describe, it, expect, vi, beforeEach } from "vitest";
import { useState } from "react";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import {
  ChangePasswordDialog,
  PASSWORD_CHANGED_NOTICE,
} from "../components/ChangePasswordDialog";
import { ApiError } from "../lib/api";

const { authState } = vi.hoisted(() => ({
  authState: { pending: false, mutate: vi.fn() },
}));

vi.mock("../queries/useAuth", () => ({
  useMe: () => ({ data: undefined, isLoading: false, error: null }),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useChangePassword: () => ({
    mutate: authState.mutate,
    isPending: authState.pending,
    reset: vi.fn(),
  }),
}));

/**
 * Mirrors how `ProfileView` owns the dialog: it opens it, and on success it
 * closes the dialog and renders the notice. Kept here so the dialog's own
 * success contract is observable in isolation.
 */
function Harness() {
  const [open, setOpen] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Abrir
      </button>
      {notice && <p role="status">{notice}</p>}
      <ChangePasswordDialog
        open={open}
        onSuccess={() => {
          setOpen(false);
          setNotice(PASSWORD_CHANGED_NOTICE);
        }}
        onCancel={() => setOpen(false)}
      />
    </div>
  );
}

function fillAndSubmit(current = "vieja-clave", next = "nueva-clave") {
  fireEvent.change(screen.getByLabelText("Contraseña actual"), {
    target: { value: current },
  });
  fireEvent.change(screen.getByLabelText("Contraseña nueva"), {
    target: { value: next },
  });
  fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
}

describe("ChangePasswordDialog", () => {
  beforeEach(() => {
    authState.pending = false;
    authState.mutate.mockReset();
  });

  it("renders the two password fields and focuses Cancel by default", () => {
    renderWithProviders(<Harness />);

    expect(screen.getByRole("dialog", { name: "Cambiar contraseña" })).toBeTruthy();
    expect(screen.getByLabelText("Contraseña actual").getAttribute("type")).toBe(
      "password",
    );
    expect(screen.getByLabelText("Contraseña nueva").getAttribute("type")).toBe(
      "password",
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Cancelar" }),
    );
  });

  it("sends both passwords to the mutation", () => {
    authState.mutate.mockImplementation(() => {});
    renderWithProviders(<Harness />);

    fillAndSubmit("actual-123", "nueva-1234");

    expect(authState.mutate).toHaveBeenCalledWith(
      { current_password: "actual-123", new_password: "nueva-1234" },
      expect.any(Object),
    );
  });

  it("maps 401 to the current-password copy inside the dialog", () => {
    authState.mutate.mockImplementation((_vars, options) =>
      options.onError(new ApiError(401, { detail: "Current password is incorrect" })),
    );
    renderWithProviders(<Harness />);

    fillAndSubmit();

    expect(screen.getByRole("alert").textContent).toBe(
      "La contraseña actual no es correcta.",
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("maps 422 to the minimum-length copy inside the dialog", () => {
    authState.mutate.mockImplementation((_vars, options) =>
      options.onError(new ApiError(422, { detail: "too short" })),
    );
    renderWithProviders(<Harness />);

    fillAndSubmit();

    expect(screen.getByRole("alert").textContent).toBe(
      "La contraseña nueva debe tener al menos 8 caracteres.",
    );
  });

  it("maps any other failure to the generic copy inside the dialog", () => {
    authState.mutate.mockImplementation((_vars, options) =>
      options.onError(new ApiError(500, {})),
    );
    renderWithProviders(<Harness />);

    fillAndSubmit();

    expect(screen.getByRole("alert").textContent).toBe(
      "No se pudo cambiar la contraseña. Vuelve a intentarlo.",
    );
  });

  it("closes the dialog and shows the notice on success", async () => {
    authState.mutate.mockImplementation((_vars, options) => options.onSuccess());
    renderWithProviders(<Harness />);

    fillAndSubmit();

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("status").textContent).toBe(PASSWORD_CHANGED_NOTICE);
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
      (screen.getByRole("button", { name: "Guardando…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
