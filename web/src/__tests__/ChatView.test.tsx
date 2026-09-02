import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, screen } from "@testing-library/react";
import { useChatStore } from "../stores/useChatStore";
import { renderWithProviders } from "./test-utils";
import ChatView from "../routes/ChatView";

// ── Hook tests (existing) ────────────────────────────────────────────────────

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

// ── Component tests (new: failure paths) ─────────────────────────────────────

const { useSessionsMock, useMessagesMock, useCreateSessionMock, useDeleteSessionMock } =
  vi.hoisted(() => ({
    useSessionsMock: vi.fn(),
    useMessagesMock: vi.fn(),
    useCreateSessionMock: vi.fn(),
    useDeleteSessionMock: vi.fn(),
  }));

vi.mock("../queries/useSessions", () => ({
  useSessions: () => useSessionsMock(),
  useCreateSession: () => useCreateSessionMock(),
  useDeleteSession: () => useDeleteSessionMock(),
}));

vi.mock("../queries/useMessages", () => ({
  useMessages: () => useMessagesMock(),
}));

vi.mock("../lib/sse", () => ({
  streamChat: vi.fn(),
}));

vi.mock("../components/ChatMessage", () => ({
  default: ({ role, content }: { role: string; content: string }) => (
    <div data-testid={`msg-${role}`}>{content}</div>
  ),
}));

describe("ChatView component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    useSessionsMock.mockReturnValue({
      data: [{ id: "ses-1", title: "Chat 1" }],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    useMessagesMock.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    useCreateSessionMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ id: "ses-new", title: "New" }),
    });
    useDeleteSessionMock.mockReturnValue({ mutate: vi.fn() });
  });

  it("renders the session sidebar heading", () => {
    renderWithProviders(<ChatView />, { route: "/app/chat" });
    expect(screen.getByText("Chat 1")).toBeTruthy();
  });

  it("shows sessions error with retry (R-ErrorUI-3)", () => {
    useSessionsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load sessions"),
      refetch: vi.fn(),
    });
    renderWithProviders(<ChatView />, { route: "/app/chat" });
    const alerts = screen.getAllByRole("alert");
    expect(alerts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("shows messages error with retry (R-ErrorUI-3)", () => {
    useMessagesMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Failed to load chat messages"),
      refetch: vi.fn(),
    });
    renderWithProviders(<ChatView />, { route: "/app/chat/ses-1" });
    const alerts = screen.getAllByRole("alert");
    expect(alerts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Retry")).toBeTruthy();
  });
});