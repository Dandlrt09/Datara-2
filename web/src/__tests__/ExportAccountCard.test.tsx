/* Tests for the account export card (T5). The card has no query: its whole job
 * is to send the browser to the export endpoint so the download streams straight
 * to disk. The navigation is stubbed and the assertions check what the user
 * reads and where the click goes. */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import ExportAccountCard from "../components/ExportAccountCard";

const { assignMock } = vi.hoisted(() => ({ assignMock: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { assign: assignMock },
  });
});

describe("ExportAccountCard", () => {
  it("names what the export contains and warns about size and time", () => {
    renderWithProviders(<ExportAccountCard />);
    expect(screen.getByText("Exportar mi cuenta")).toBeTruthy();
    expect(screen.getByText(/chats/i)).toBeTruthy();
    expect(screen.getByText(/puede pesar/i)).toBeTruthy();
  });

  it("navigates to the export endpoint when the button is clicked", () => {
    renderWithProviders(<ExportAccountCard />);
    fireEvent.click(screen.getByRole("button", { name: /descargar/i }));
    expect(assignMock).toHaveBeenCalledWith("/api/export/account");
  });
});
