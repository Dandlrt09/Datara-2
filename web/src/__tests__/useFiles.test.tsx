import { describe, it, expect, expectTypeOf, vi, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useUploadFile, UploadError, useFileSheets, useSelectFileSheet } from "../queries/useFiles";
import type { FileCreateResult, ProfileSummary, UploadedFile } from "../queries/useFiles";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return wrapper;
}

describe("useUploadFile", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("threads the AbortSignal into the upload fetch", async () => {
    // Never-resolving fetch keeps the mutation in-flight for inspection.
    const fetchMock = vi.fn(
      (..._args: unknown[]) => new Promise<Response>(() => {}),
    );
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useUploadFile(), { wrapper });

    const controller = new AbortController();
    result.current.mutate({
      sessionId: "ses-1",
      file: new File(["name,age\nAlice,30\n"], "a.csv"),
      signal: controller.signal,
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBe(controller.signal);

    controller.abort();
    expect((init.signal as AbortSignal).aborted).toBe(true);
  });

  it("works without a signal (backwards compatible)", async () => {
    const fetchMock = vi.fn(
      (..._args: unknown[]) => new Promise<Response>(() => {}),
    );
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = makeWrapper();
    const { result } = renderHook(() => useUploadFile(), { wrapper });

    result.current.mutate({
      sessionId: "ses-1",
      file: new File(["name,age\nAlice,30\n"], "a.csv"),
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBeUndefined();
  });

  it("rejects with an UploadError carrying the status and server detail", async () => {
    const detail =
      "A file named 'a.csv' already exists in this session. Delete it first.";
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 409,
      json: async () => ({ detail }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUploadFile(), {
      wrapper: makeWrapper(),
    });

    let caught: unknown;
    try {
      await result.current.mutateAsync({
        sessionId: "ses-1",
        file: new File(["x"], "a.csv"),
      });
    } catch (e) {
      caught = e;
    }

    expect(caught).toBeInstanceOf(UploadError);
    expect((caught as UploadError).status).toBe(409);
    expect((caught as UploadError).message).toBe(detail);
  });

  it("falls back to the status message when the error body is not JSON", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 400,
      json: async () => {
        throw new SyntaxError("Unexpected token < in JSON");
      },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUploadFile(), {
      wrapper: makeWrapper(),
    });

    let caught: unknown;
    try {
      await result.current.mutateAsync({
        sessionId: "ses-1",
        file: new File(["x"], "a.csv"),
      });
    } catch (e) {
      caught = e;
    }

    expect(caught).toBeInstanceOf(UploadError);
    expect((caught as UploadError).status).toBe(400);
    expect((caught as UploadError).message).toBe("Upload failed: 400");
  });

  it("resolves the upload to the exact FileCreateResponse payload (no profile_summary)", async () => {
    // The POST /api/sessions/{id}/files response model is FileCreateResponse.
    // It never carries a profile_summary, so the mutation result must be the
    // payload verbatim and must not fabricate a key.
    const payload = {
      id: 42,
      filename: "book.xlsx",
      format: "xlsx",
      size_bytes: 2048,
      row_count: 3,
      encoding: null,
      sheet_name: "Data",
      sheets: ["Data", "Meta"],
      created_at: "2026-09-25T10:00:00Z",
    };
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 201,
      json: async () => payload,
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUploadFile(), {
      wrapper: makeWrapper(),
    });

    const uploaded = await result.current.mutateAsync({
      sessionId: "ses-1",
      file: new File(["name,age\nAlice,30\n"], "book.xlsx"),
    });

    expect(uploaded).toEqual(payload);
    expect("profile_summary" in uploaded).toBe(false);
  });

  it("pins the corrected types to their server models", () => {
    // Type-level pins: compiled by `tsc -b` (tsconfig includes src/), so a
    // drift back to the old shapes fails `npm run build`, not just this test.
    // Pin the EXACT key sets, not individual keys: the F7 defect class is a
    // fabricated field, so an arbitrary added key must fail here too.
    expectTypeOf<FileCreateResult>().not.toHaveProperty("profile_summary");
    expectTypeOf<keyof FileCreateResult>().toEqualTypeOf<
      | "id"
      | "filename"
      | "format"
      | "size_bytes"
      | "row_count"
      | "encoding"
      | "sheet_name"
      | "sheets"
      | "created_at"
    >();
    expectTypeOf<keyof UploadedFile>().toEqualTypeOf<
      | "id"
      | "filename"
      | "format"
      | "size_bytes"
      | "row_count"
      | "created_at"
      | "has_profile"
    >();
    expectTypeOf<keyof ProfileSummary>().toEqualTypeOf<
      "file_id" | "schema" | "stats" | "sample" | "generated_at"
    >();
    expectTypeOf<ProfileSummary["schema"]["columns"]>().toEqualTypeOf<
      { name: string; dtype: string }[]
    >();
  });
});

describe("useFileSheets", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests the file's sheet list", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({
      ok: true,
      status: 200,
      json: async () => ({ sheets: ["Data", "Meta"], default_sheet: "Data" }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useFileSheets(5), {
      wrapper: makeWrapper(),
    });

    await waitFor(() =>
      expect(result.current.data?.sheets).toEqual(["Data", "Meta"])
    );
    expect(fetchMock.mock.calls[0][0]).toBe("/api/files/5/sheets");
  });

  it("does not fetch when fileId is null", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderHook(() => useFileSheets(null), { wrapper: makeWrapper() });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not fetch when disabled", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderHook(() => useFileSheets(5, false), { wrapper: makeWrapper() });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("useSelectFileSheet", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs the sheet name and invalidates the files + profile queries", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({
      ok: true,
      status: 200,
      json: async () => ({
        file_id: 5,
        filename: "book.xlsx",
        sheet_name: "Meta",
        sheets: ["Data", "Meta"],
        row_count: 1,
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const qc = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useSelectFileSheet(), { wrapper });

    await result.current.mutateAsync({ fileId: 5, sheetName: "Meta" });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/files/5/sheet");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ sheet_name: "Meta" }));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["files"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["profile", 5] });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["file-sheets", 5],
    });
  });
});
