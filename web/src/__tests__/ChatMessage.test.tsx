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

describe("ChatMessage token meta line", () => {
  it("renders total tokens with Spanish thousands separators plus estimated cost", () => {
    render(
      <ChatMessage
        role="assistant"
        content="respuesta"
        tokensIn={1234}
        tokensOut={234}
        costUsd={0.125}
      />,
    );
    // 1234 + 234 = 1468 → dot thousands separator; cost with decimal comma.
    expect(screen.getByText("1.468 tokens · US$ 0,1250")).toBeTruthy();
  });

  it("hides the meta line entirely when usage is null (legacy rows)", () => {
    render(
      <ChatMessage
        role="assistant"
        content="respuesta"
        tokensIn={null}
        tokensOut={null}
        costUsd={null}
      />,
    );
    expect(screen.queryByText(/tokens/)).toBeNull();
    expect(screen.queryByText(/US\$/)).toBeNull();
  });

  it("shows 'costo no disponible' when the model has no price entry", () => {
    render(
      <ChatMessage
        role="assistant"
        content="respuesta"
        tokensIn={50}
        tokensOut={100}
        costUsd={null}
      />,
    );
    expect(screen.getByText(/150 tokens/)).toBeTruthy();
    expect(screen.getByText(/costo no disponible/)).toBeTruthy();
    expect(screen.queryByText(/US\$/)).toBeNull();
  });

  it("never renders the meta line for user messages", () => {
    render(
      <ChatMessage role="user" content="pregunta" tokensIn={50} tokensOut={100} />,
    );
    expect(screen.queryByText(/tokens/)).toBeNull();
  });
});

describe("ChatMessage edit affordance", () => {
  it("shows Editar for a user message with onEdit", () => {
    render(
      <ChatMessage role="user" content="pregunta" messageId={7} onEdit={vi.fn()} />,
    );
    expect(screen.getByText("Editar")).toBeTruthy();
  });

  it("hides Editar when onEdit is not provided (parent-controlled availability)", () => {
    render(<ChatMessage role="user" content="pregunta" messageId={7} />);
    expect(screen.queryByText("Editar")).toBeNull();
  });

  it("hides Editar for assistant messages even with onEdit", () => {
    render(
      <ChatMessage
        role="assistant"
        content="respuesta"
        messageId={7}
        onEdit={vi.fn()}
      />,
    );
    expect(screen.queryByText("Editar")).toBeNull();
  });

  it("saves the edited text via onEdit(id, text) and leaves edit mode", () => {
    const onEdit = vi.fn();
    render(
      <ChatMessage role="user" content="pregunta" messageId={7} onEdit={onEdit} />,
    );

    fireEvent.click(screen.getByText("Editar"));
    const textarea = screen.getByLabelText("Editar pregunta") as HTMLTextAreaElement;
    expect(textarea.value).toBe("pregunta");

    fireEvent.change(textarea, { target: { value: "  pregunta corregida  " } });
    fireEvent.click(screen.getByText("Guardar"));

    expect(onEdit).toHaveBeenCalledWith(7, "pregunta corregida");
    expect(screen.queryByLabelText("Editar pregunta")).toBeNull();
  });

  it("disables Guardar when the trimmed text is empty or unchanged", () => {
    const onEdit = vi.fn();
    render(
      <ChatMessage role="user" content="pregunta" messageId={7} onEdit={onEdit} />,
    );
    fireEvent.click(screen.getByText("Editar"));
    const textarea = screen.getByLabelText("Editar pregunta");

    // Unchanged → disabled.
    expect((screen.getByText("Guardar") as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(textarea, { target: { value: "   " } });
    expect((screen.getByText("Guardar") as HTMLButtonElement).disabled).toBe(true);
    expect(onEdit).not.toHaveBeenCalled();
  });

  it("renders the truncation warning only when hasLaterMessages is true", () => {
    const warning =
      "Se van a eliminar las preguntas y respuestas posteriores a esta.";

    const withLater = render(
      <ChatMessage
        role="user"
        content="pregunta"
        messageId={1}
        onEdit={vi.fn()}
        hasLaterMessages
      />,
    );
    fireEvent.click(screen.getByText("Editar"));
    expect(screen.getByText(warning)).toBeTruthy();
    withLater.unmount();

    render(
      <ChatMessage
        role="user"
        content="pregunta"
        messageId={1}
        onEdit={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Editar"));
    expect(screen.queryByText(warning)).toBeNull();
  });

  it("Cancelar leaves edit mode without calling onEdit", () => {
    const onEdit = vi.fn();
    render(
      <ChatMessage role="user" content="pregunta" messageId={7} onEdit={onEdit} />,
    );
    fireEvent.click(screen.getByText("Editar"));
    fireEvent.change(screen.getByLabelText("Editar pregunta"), {
      target: { value: "cambio descartado" },
    });
    fireEvent.click(screen.getByText("Cancelar"));

    expect(onEdit).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Editar pregunta")).toBeNull();
    expect(screen.getByText("pregunta")).toBeTruthy();
  });

  it("plain Enter inserts a newline; Ctrl+Enter saves", () => {
    const onEdit = vi.fn();
    render(
      <ChatMessage role="user" content="pregunta" messageId={7} onEdit={onEdit} />,
    );
    fireEvent.click(screen.getByText("Editar"));
    const textarea = screen.getByLabelText("Editar pregunta") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "linea uno" } });

    // Plain Enter must not submit (multi-line questions).
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onEdit).not.toHaveBeenCalled();

    // Ctrl+Enter submits.
    fireEvent.keyDown(textarea, { key: "Enter", ctrlKey: true });
    expect(onEdit).toHaveBeenCalledWith(7, "linea uno");
  });

  it("Escape cancels the edit without calling onEdit", () => {
    const onEdit = vi.fn();
    render(
      <ChatMessage role="user" content="pregunta" messageId={7} onEdit={onEdit} />,
    );
    fireEvent.click(screen.getByText("Editar"));
    const textarea = screen.getByLabelText("Editar pregunta");
    fireEvent.change(textarea, { target: { value: "cambio" } });
    fireEvent.keyDown(textarea, { key: "Escape" });

    expect(onEdit).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Editar pregunta")).toBeNull();
  });
});

describe("ChatMessage regenerate affordance", () => {
  it("shows Regenerar for an assistant message with onRegenerate", () => {
    render(
      <ChatMessage
        role="assistant"
        content="respuesta"
        onRegenerate={vi.fn()}
      />,
    );
    expect(screen.getByText("Regenerar")).toBeTruthy();
  });

  it("hides Regenerar when onRegenerate is not provided (parent-controlled availability)", () => {
    render(<ChatMessage role="assistant" content="respuesta" />);
    expect(screen.queryByText("Regenerar")).toBeNull();
  });

  it("hides Regenerar for user messages even with onRegenerate", () => {
    render(
      <ChatMessage
        role="user"
        content="pregunta"
        messageId={7}
        onRegenerate={vi.fn()}
      />,
    );
    expect(screen.queryByText("Regenerar")).toBeNull();
  });

  it("calls onRegenerate exactly once when clicked", () => {
    const onRegenerate = vi.fn();
    render(
      <ChatMessage
        role="assistant"
        content="respuesta"
        onRegenerate={onRegenerate}
      />,
    );

    fireEvent.click(screen.getByText("Regenerar"));

    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });
});
