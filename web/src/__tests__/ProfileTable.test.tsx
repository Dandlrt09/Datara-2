import { describe, it, expect } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { ProfileTable } from "../components/ProfileTable";
import type { ProfileSummary } from "../queries/useFiles";

function makeProfile(overrides: Partial<ProfileSummary> = {}): ProfileSummary {
  return {
    file_id: 1,
    schema: { columns: [{ name: "amount", dtype: "int64" }] },
    stats: {
      amount: {
        null_count: 3,
        unique_count: 1200,
        min: 1,
        max: 1234.5,
      },
    },
    sample: [],
    generated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("ProfileTable", () => {
  it("renders the six column headers", () => {
    renderWithProviders(<ProfileTable profile={makeProfile()} />);

    for (const header of ["Columna", "Tipo", "Nulos", "Únicos", "Mín", "Máx"]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeTruthy();
    }
  });

  it("renders one row per schema column with formatted stats", () => {
    renderWithProviders(<ProfileTable profile={makeProfile()} />);

    const row = screen.getByText("amount").closest("tr");
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement);
    expect(cells.getByText("int64")).toBeTruthy();
    expect(cells.getByText("3")).toBeTruthy();
    expect(cells.getByText("1.200")).toBeTruthy();
    expect(cells.getByText("1")).toBeTruthy();
    expect(cells.getByText("1.234,5")).toBeTruthy();
  });

  it("renders an em dash for null or missing stat values", () => {
    renderWithProviders(
      <ProfileTable
        profile={makeProfile({
          schema: {
            columns: [
              { name: "text_col", dtype: "object" },
              { name: "missing_col", dtype: "float64" },
            ],
          },
          stats: {
            text_col: { null_count: null, unique_count: undefined, min: null, max: null },
          },
        })}
      />
    );

    const textRow = screen.getByText("text_col").closest("tr") as HTMLElement;
    expect(within(textRow).getAllByText("—").length).toBe(4);

    const missingRow = screen.getByText("missing_col").closest("tr") as HTMLElement;
    expect(within(missingRow).getAllByText("—").length).toBe(4);
  });

  it("keeps the raw JSON reachable in a nested Raw JSON collapsible", () => {
    renderWithProviders(<ProfileTable profile={makeProfile()} />);

    const summary = screen.getByText("Raw JSON");
    expect(summary).toBeTruthy();

    const pre = summary.parentElement?.querySelector("pre");
    // Acceptance 3: the nested dump must be byte-identical to the old raw dump.
    expect(pre?.textContent).toBe(JSON.stringify(makeProfile(), null, 2));
  });

  it("does not throw on an empty stats object", () => {
    expect(() =>
      renderWithProviders(<ProfileTable profile={makeProfile({ stats: {} })} />)
    ).not.toThrow();

    const row = screen.getByText("amount").closest("tr") as HTMLElement;
    expect(within(row).getAllByText("—").length).toBe(4);
  });

  it("does not throw on a null stats object or empty schema", () => {
    expect(() =>
      renderWithProviders(
        <ProfileTable
          profile={makeProfile({
            schema: { columns: [] },
            stats: null as unknown as Record<string, unknown>,
          })}
        />
      )
    ).not.toThrow();

    // Headers still render even with no rows.
    expect(screen.getByRole("columnheader", { name: "Tipo" })).toBeTruthy();
    expect(screen.getByText("Raw JSON")).toBeTruthy();
  });
});
