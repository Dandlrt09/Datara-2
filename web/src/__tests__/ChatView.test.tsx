import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useChatStore } from "../stores/useChatStore";

describe("useChatStore", () => {
  it("accumulates streaming text", () => {
    const { result } = renderHook(() => useChatStore());

    act(() => {
      result.current.appendStreamingText("Hello");
    });
    expect(result.current.streamingText).toBe("Hello");

    act(() => {
      result.current.appendStreamingText(" World");
    });
    expect(result.current.streamingText).toBe("Hello World");
  });

  it("clears streaming text", () => {
    const { result } = renderHook(() => useChatStore());

    act(() => {
      result.current.appendStreamingText("Hello");
    });
    act(() => {
      result.current.clearStreamingText();
    });
    expect(result.current.streamingText).toBe("");
  });

  it("sets streaming state", () => {
    const { result } = renderHook(() => useChatStore());

    act(() => {
      result.current.setStreaming(true);
    });
    expect(result.current.isStreaming).toBe(true);
  });

  it("sets pending artifacts", () => {
    const { result } = renderHook(() => useChatStore());
    const artifacts = { figures: [{ name: "fig1" }], tables: [] };

    act(() => {
      result.current.setPendingArtifacts(artifacts);
    });
    expect(result.current.pendingArtifacts).toEqual(artifacts);
  });

  it("sets active session id", () => {
    const { result } = renderHook(() => useChatStore());

    act(() => {
      result.current.setActiveSessionId("ses-123");
    });
    expect(result.current.activeSessionId).toBe("ses-123");
  });
});