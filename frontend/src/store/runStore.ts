import { create } from "zustand";
import { persist } from "zustand/middleware";

type ChatRunState = {
  activeChatRunId: string | null;
  activeChatSessionId: string | null;
  activeChatRunStatus: string | null;
  activeChatRunStartedAt: string | null;
  activeChatRunError: string | null;
  activeChatRunStep: string | null;
  activeChatRunMessage: string | null;
  activeChatRunPercent: number | null;
  setActiveChatRun: (payload: { runId: string; sessionId: string; status: string; startedAt?: string | null; step?: string | null; message?: string | null; percent?: number | null }) => void;
  updateActiveChatRunStatus: (status: string, error?: string | null, progress?: { step?: string | null; message?: string | null; percent?: number | null }) => void;
  clearActiveChatRun: () => void;
};

export const useRunStore = create<ChatRunState>()(
  persist(
    (set) => ({
      activeChatRunId: null,
      activeChatSessionId: null,
      activeChatRunStatus: null,
      activeChatRunStartedAt: null,
      activeChatRunError: null,
      activeChatRunStep: null,
      activeChatRunMessage: null,
      activeChatRunPercent: null,
      setActiveChatRun: ({ runId, sessionId, status, startedAt, step, message, percent }) =>
        set({
          activeChatRunId: runId,
          activeChatSessionId: sessionId,
          activeChatRunStatus: status,
          activeChatRunStartedAt: startedAt ?? new Date().toISOString(),
          activeChatRunError: null,
          activeChatRunStep: step ?? null,
          activeChatRunMessage: message ?? null,
          activeChatRunPercent: percent ?? null,
        }),
      updateActiveChatRunStatus: (activeChatRunStatus, activeChatRunError = null, progress) =>
        set({
          activeChatRunStatus,
          activeChatRunError,
          activeChatRunStep: progress?.step ?? null,
          activeChatRunMessage: progress?.message ?? null,
          activeChatRunPercent: progress?.percent ?? null,
        }),
      clearActiveChatRun: () =>
        set({
          activeChatRunId: null,
          activeChatSessionId: null,
          activeChatRunStatus: null,
          activeChatRunStartedAt: null,
          activeChatRunError: null,
          activeChatRunStep: null,
          activeChatRunMessage: null,
          activeChatRunPercent: null,
        }),
    }),
    {
      name: "mindos-run-store",
    },
  ),
);
