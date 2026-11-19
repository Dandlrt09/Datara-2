import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import FirstRunScreen from "../routes/FirstRunScreen";
import { ApiError } from "../lib/api";

/* The screen talks to the network through the shared `api` wrapper, so the
 * tests mock that wrapper (not the hooks) and let the real queries/mutation
 * run. That way the error mapping and the auto-open live under test too. */
const { apiMock, getMock, postMock, navigateMock } = vi.hoisted(() => {
  const getMock = vi.fn();
  const postMock = vi.fn();
  return {
    getMock,
    postMock,
    apiMock: {
      get: getMock,
      post: postMock,
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
    },
    navigateMock: vi.fn(),
  };
});

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, api: apiMock };
});

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

/** Network the mocked wrapper answers: the session check and the local-profile
 * probe. `user` null means "no session" (the check rejects with 401). */
const net: { user: unknown; exists: boolean } = { user: null, exists: false };

beforeEach(() => {
  vi.clearAllMocks();
  net.user = null;
  net.exists = false;
  navigateMock.mockReset();
  getMock.mockImplementation((url: string) => {
    if (url === "/api/auth/me") {
      return net.user
        ? Promise.resolve(net.user)
        : Promise.reject(new ApiError(401, {}));
    }
    if (url === "/api/auth/local-profile") {
      return Promise.resolve({ exists: net.exists });
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
  postMock.mockResolvedValue({
    id: 1,
    email: null,
    name: "Ana",
    pending_deletion_at: null,
  });
});

describe("FirstRunScreen (F1 / T2c)", () => {
  it("shows the creation form when there is no local profile", async () => {
    renderWithProviders(<FirstRunScreen />);

    expect(
      await screen.findByRole("heading", { name: "Crea tu perfil" }),
    ).toBeTruthy();
    expect(screen.getByRole("textbox")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Crear perfil" })).toBeTruthy();
    expect(postMock).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("refuses a blank name", async () => {
    postMock.mockRejectedValue(
      new ApiError(422, { detail: "Name is required" }),
    );

    renderWithProviders(<FirstRunScreen />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Crear perfil" }),
    );

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/api/auth/local-profile", {
        name: "",
      }),
    );
    expect(
      await screen.findByText("Escribe un nombre para tu perfil."),
    ).toBeTruthy();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("creates the profile with a valid name and lands on /app", async () => {
    renderWithProviders(<FirstRunScreen />);
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "Ana" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear perfil" }));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/api/auth/local-profile", {
        name: "Ana",
      }),
    );
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/app", { replace: true }),
    );
  });

  it("opens an existing profile automatically, with no click", async () => {
    net.exists = true;

    renderWithProviders(<FirstRunScreen />);

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/api/auth/local-profile", {}),
    );
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/app", { replace: true }),
    );
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("shows the retry when the automatic open fails", async () => {
    net.exists = true;
    postMock.mockRejectedValueOnce(new ApiError(500, { detail: "boom" }));

    renderWithProviders(<FirstRunScreen />);

    const retry = await screen.findByRole("button", {
      name: "Vuelve a intentarlo",
    });
    expect(navigateMock).not.toHaveBeenCalled();

    fireEvent.click(retry);

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/app", { replace: true }),
    );
  });

  it("sends an already signed-in visitor straight to /app", async () => {
    net.user = { id: 1, email: null, name: "Ana", pending_deletion_at: null };

    renderWithProviders(<FirstRunScreen />);

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/app", { replace: true }),
    );
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(postMock).not.toHaveBeenCalled();
  });
});
