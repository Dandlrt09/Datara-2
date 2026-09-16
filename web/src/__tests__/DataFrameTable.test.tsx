import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import DataFrameTable, { buildCsv } from "../components/DataFrameTable";

describe("buildCsv", () => {
  it("prepends a UTF-8 BOM and joins lines with \\n", () => {
    const csv = buildCsv(["a", "b"], [["1", "2"]]);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    expect(csv.slice(1)).toBe("a,b\n1,2\n");
    expect(csv.includes("\r")).toBe(false);
  });

  it("quotes fields containing commas", () => {
    const csv = buildCsv(["col"], [["x,y"]]);
    expect(csv).toBe("\uFEFFcol\n\"x,y\"\n");
  });

  it("doubles embedded quotes inside quoted fields", () => {
    const csv = buildCsv(["col"], [['a"b']]);
    expect(csv).toBe("\uFEFFcol\n\"a\"\"b\"\n");
  });

  it("quotes fields containing newlines", () => {
    const csv = buildCsv(["col"], [["line1\nline2"]]);
    expect(csv).toBe("\uFEFFcol\n\"line1\nline2\"\n");
  });

  it("renders null/undefined cells as empty fields", () => {
    const csv = buildCsv(["a", "b"], [[null, undefined]]);
    expect(csv).toBe("\uFEFFa,b\n,\n");
  });
});

describe("DataFrameTable CSV download", () => {
  const createObjectURL = vi.fn((_blob: Blob) => "blob:mock-url");
  const revokeObjectURL = vi.fn();
  let clickSpy: ReturnType<typeof vi.spyOn>;

  // jsdom's FileReader.readAsText strips the BOM, so read the raw bytes and
  // assert the UTF-8 BOM explicitly before decoding the rest.
  function readBlobBytes(blob: Blob): Promise<Uint8Array> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(blob);
    });
  }

  async function readBlobText(blob: Blob): Promise<string> {
    const bytes = await readBlobBytes(blob);
    // UTF-8 BOM: EF BB BF
    expect([bytes[0], bytes[1], bytes[2]]).toEqual([0xef, 0xbb, 0xbf]);
    return new TextDecoder("utf-8").decode(bytes.subarray(3));
  }

  beforeEach(() => {
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
    Object.defineProperty(URL, "createObjectURL", {
      value: createObjectURL,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeObjectURL,
      configurable: true,
      writable: true,
    });
    clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
  });

  afterEach(() => {
    clickSpy.mockRestore();
  });

  it("downloads the visible (sorted) rows as datara-tabla.csv", async () => {
    render(
      <DataFrameTable
        columns={["ciudad", "ventas"]}
        rows={[
          ["Rosario", 20],
          ["Córdoba", 10],
        ]}
      />,
    );

    // Sort by first column ascending: Córdoba must come first in the CSV.
    fireEvent.click(screen.getByText(/ciudad/));
    fireEvent.click(screen.getByText("Descargar CSV"));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0][0];
    expect(blob.type).toContain("text/csv");

    expect(await readBlobText(blob)).toBe(
      "ciudad,ventas\nCórdoba,10\nRosario,20\n",
    );

    const anchor = clickSpy.mock.contexts[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("datara-tabla.csv");
    expect(anchor.href).toBe("blob:mock-url");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });

  it("exports the raw order when no sort is active", async () => {
    render(
      <DataFrameTable columns={["x"]} rows={[[2], [1]]} />,
    );

    fireEvent.click(screen.getByText("Descargar CSV"));
    const blob = createObjectURL.mock.calls[0][0];
    expect(await readBlobText(blob)).toBe("x\n2\n1\n");
  });
});
