import { create } from "zustand";

interface ChatState {
  activeSessionId: string | null;
  setActiveSessionId: (id: string | null) => void;
  streamingText: string;
  appendStreamingText: (delta: string) => void;
  clearStreamingText: () => void;
  pendingArtifacts: { figures: unknown[]; tables: unknown[] } | null;
  setPendingArtifacts: (artifacts: { figures: unknown[]; tables: unknown[] } | null) => void;
  isStreaming: boolean;
  setStreaming: (v: boolean) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  activeSessionId: null,
  setActiveSessionId: (id) => set({ activeSessionId: id }),
  streamingText: "",
  appendStreamingText: (delta) =>
    set((s) => ({ streamingText: s.streamingText + delta })),
  clearStreamingText: () => set({ streamingText: "" }),
  pendingArtifacts: null,
  setPendingArtifacts: (artifacts) => set({ pendingArtifacts: artifacts }),
  isStreaming: false,
  setStreaming: (v) => set({ isStreaming: v }),
}));