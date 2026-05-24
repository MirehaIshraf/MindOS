import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { healthCheck } from "../../services/api";
import { useAppStore } from "../../store/appStore";
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
  const {
    activePageTitle,
    backendOnline,
    storageMode,
    setActivePageTitle,
    setBackendOnline,
    setStorageMode,
  } = useAppStore();

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

  return (
    <header className="fixed left-[260px] right-0 top-0 z-10 flex h-16 items-center justify-between border-b border-app-border bg-app-background/95 px-8 backdrop-blur">
      <div>
        <p className="text-xs uppercase text-app-muted">Workspace</p>
        <h2 className="text-lg font-semibold text-app-text">{activePageTitle}</h2>
      </div>
      <div className="flex items-center gap-3">
        {storageMode ? <Badge variant="info">{storageMode}</Badge> : null}
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
