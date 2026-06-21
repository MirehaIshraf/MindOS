import { Moon, Sun } from "lucide-react";
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { getChatRun, healthCheck } from "../../services/api";
import { useAppStore } from "../../store/appStore";
import { useRunStore } from "../../store/runStore";
import { Badge } from "../shared/Badge";

const titles: Record<string, string> = {
  "/chat": "Chat",
  "/memory": "Memory",
  "/tasks": "Tasks",
  "/connectors": "Connectors",
  "/playbooks": "Playbooks",
  "/settings": "Settings",
  "/dev": "Developer Mode",
};

export function TopBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const {
    activePageTitle,
    backendOnline,
    storageMode,
    theme,
    setActivePageTitle,
    setBackendOnline,
    setStorageMode,
    toggleTheme,
  } = useAppStore();
  const { activeChatRunId, activeChatRunStatus, updateActiveChatRunStatus, clearActiveChatRun } = useRunStore();
  const chatRunning = Boolean(activeChatRunId && ["queued", "running"].includes(activeChatRunStatus ?? ""));

  useEffect(() => {
    setActivePageTitle(titles[location.pathname] ?? "MindOS");
  }, [location.pathname, setActivePageTitle]);

  useEffect(() => {
    let active = true;

    async function checkBackend() {
      try {
        const health = await healthCheck();
        if (!active) {
          return;
        }
        setBackendOnline(true);
        setStorageMode(health.storage);
      } catch {
        if (!active) {
          return;
        }
        setBackendOnline(false);
        setStorageMode(null);
      }
    }

    void checkBackend();
    const intervalId = window.setInterval(checkBackend, 30_000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [setBackendOnline, setStorageMode]);

  useEffect(() => {
    if (!activeChatRunId) {
      return;
    }
    let active = true;
    const runId = activeChatRunId;

    async function checkRun() {
      try {
        const run = await getChatRun(runId);
        if (!active) {
          return;
        }
        updateActiveChatRunStatus(run.status, run.error ?? null, {
          step: run.current_step,
          message: run.progress_message,
          percent: run.progress_percent,
        });
        if (!["queued", "running"].includes(run.status)) {
          // On the chat page, let the ChatPage poller load the reply messages and
          // then clear — clearing here first would tear down its poll and drop the
          // reply. Off the chat page there's no message view to update, so clear.
          if (window.location.pathname !== "/chat") {
            clearActiveChatRun();
          }
        }
      } catch {
        if (active) {
          clearActiveChatRun();
        }
      }
    }

    void checkRun();
    const intervalId = window.setInterval(checkRun, 3_000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [activeChatRunId, clearActiveChatRun, updateActiveChatRunStatus]);

  return (
    <header className="fixed left-[260px] right-0 top-0 z-10 flex h-16 items-center justify-between border-b border-app-border bg-app-background/95 px-8 backdrop-blur">
      <div>
        <p className="text-xs uppercase text-app-muted">Workspace</p>
        <h2 className="text-lg font-semibold text-app-text">{activePageTitle}</h2>
      </div>
      <div className="flex items-center gap-3">
        {chatRunning ? (
          <button
            type="button"
            onClick={() => navigate("/chat")}
            className="flex items-center gap-2 rounded-md border border-app-primary/40 bg-app-primary/10 px-3 py-2 text-sm text-app-text hover:border-app-primary"
          >
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-app-primary" aria-hidden="true" />
            Chat running...
          </button>
        ) : null}
        {storageMode ? <Badge variant="info">{storageMode}</Badge> : null}
        <button
          type="button"
          onClick={toggleTheme}
          className="flex h-9 w-9 items-center justify-center rounded-md border border-app-border bg-app-panel text-app-muted transition hover:text-app-text"
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-panel px-3 py-2 text-sm text-app-muted">
          <span
            className={`h-2.5 w-2.5 rounded-full ${backendOnline ? "bg-emerald-400" : "bg-red-400"}`}
            aria-hidden="true"
          />
          <span>{backendOnline ? "Backend online" : "Backend offline"}</span>
        </div>
      </div>
    </header>
  );
}
