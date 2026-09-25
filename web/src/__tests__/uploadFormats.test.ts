import { describe, it, expect } from "vitest";
import {
  SUPPORTED_UPLOAD_EXTENSIONS,
  UPLOAD_ACCEPT_MAP,
  UPLOAD_ACCEPT_ATTR,
} from "../lib/uploadFormats";

// F6: the client accept-list must mirror the server allow-list
// (server/api/routers/files.py::_SUPPORTED_EXTENSIONS). `.tab` is rejected
// server-side with HTTP 400, so the UI must never offer it.
describe("uploadFormats", () => {
  it("never offers .tab, which the server rejects", () => {
    expect(SUPPORTED_UPLOAD_EXTENSIONS).not.toContain(".tab");
  });

  it("only maps extensions that are in the supported list", () => {
    for (const ext of Object.values(UPLOAD_ACCEPT_MAP).flat()) {
      expect(SUPPORTED_UPLOAD_EXTENSIONS).toContain(ext);
    }
  });

  it("maps exactly the supported extensions, no more and no less", () => {
    const mapped = new Set(Object.values(UPLOAD_ACCEPT_MAP).flat());
    expect([...mapped].sort()).toEqual([...SUPPORTED_UPLOAD_EXTENSIONS].sort());
  });

  it("builds an accept attribute without .tab and with .tsv", () => {
    expect(UPLOAD_ACCEPT_ATTR).not.toContain(".tab");
    expect(UPLOAD_ACCEPT_ATTR).toContain(".tsv");
  });
});
