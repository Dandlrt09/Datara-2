import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import ChatMessage from "../components/ChatMessage";

const EXACT_CODE = "df = load()\nprint(df.head())";

const writeTextMock = vi.fn();

beforeEach(() => {
  writeTextMock.mockReset();
  // jsdom does not implement the clipboard API — install a writable mock
  // (configurable so each suite gets a clean property).
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: writeTextMock },
    configurable: true,
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ChatMessage code block", () => {
  it("renders the Python code block for assistant messages with code", () => {
    render(
      <ChatMessage
        role="assistant"
        content="Respuesta con **negritas**."
        code={EXACT_CODE}
      />,
    );
    expect(screen.getByText("Python")).toBeTruthy();
    expect(screen.getByText("Copiar")).toBeTruthy();
    // The <code> element carries the exact code verbatim (no ** parsing,
    // no trimming) — it is what the sandbox actually executed.
    const codeEl = screen.getByText(/print\(df\.head\(\)\)/);
    expect(codeEl.tagName).toBe("CODE");
    expect(codeEl.textContent).toBe(EXACT_CODE);
  });

  it("does not render the code block for user messages", () => {
    render(<ChatMessage role="user" content="pregunta" code={EXACT_CODE} />);
    expect(screen.queryByText("Python")).toBeNull();
    expect(screen.queryByText("Copiar")).toBeNull();
  });

  it("does not render the code block when code is empty or whitespace-only", () => {
    render(<ChatMessage role="assistant" content="respuesta" code={"   \n "} />);
    expect(screen.queryByText("Python")).toBeNull();
    expect(screen.queryByText("Copiar")).toBeNull();
  });

  it("does not render the code block when code is null", () => {
    render(<ChatMessage role="assistant" content="respuesta" code={null} />);
    expect(screen.queryByText("Python")).toBeNull();
  });

  it("copies the exact code to the clipboard and shows transient Copiado feedback", async () => {
    writeTextMock.mockResolvedValue(undefined);
    vi.useFakeTimers();
    render(
      <ChatMessage role="assistant" content="respuesta" code={EXACT_CODE} />,
    );

    await act(async () => {
      fireEvent.click(screen.getByText("Copiar"));
    });
    expect(writeTextMock).toHaveBeenCalledWith(EXACT_CODE);
    expect(screen.getByText("Copiado")).toBeTruthy();

    // Feedback reverts to the idle label after ~2s.
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByText("Copiar")).toBeTruthy();
    expect(screen.queryByText("Copiado")).toBeNull();
  });

  it("shows an error state when the clipboard write fails and recovers", async () => {
    writeTextMock.mockRejectedValue(new Error("permission denied"));
    vi.useFakeTimers();
    render(
      <ChatMessage role="assistant" content="respuesta" code={EXACT_CODE} />,
    );

    await act(async () => {
      fireEvent.click(screen.getByText("Copiar"));
    });
    expect(screen.getByText("Error")).toBeTruthy();
    expect(
      screen.getByTitle("No se pudo copiar el código al portapapeles"),
    ).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByText("Copiar")).toBeTruthy();
  });
});
