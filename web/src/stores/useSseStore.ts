import { create } from "zustand";

export type SseState = "connecting" | "open" | "reconnecting" | "fatal";

interface SseStateData {
  sseConnected: boolean;
  sseState: SseState;
  setSseState: (state: SseState) => void;
}

export const useSseStore = create<SseStateData>((set) => ({
  sseConnected: false,
  sseState: "connecting",
  setSseState: (state) =>
    set({ sseState: state, sseConnected: state === "open" }),
}));