import {
  Bot,
  Cable,
  Code2,
  Database,
  MessageSquare,
  Settings,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAppStore } from "../../store/appStore";

const navItems = [
  { label: "Chat", path: "/chat", icon: MessageSquare, primary: true },
  { label: "Memory", path: "/memory", icon: Database },
  { label: "Connectors", path: "/connectors", icon: Cable },
  { label: "Settings", path: "/settings", icon: Settings },
  { label: "Dev", path: "/dev", icon: Code2, devOnly: true },
];

export function Sidebar() {
  const storageMode = useAppStore((state) => state.storageMode);
  const devMode = useAppStore((state) => state.devMode);
  const toggleDevMode = useAppStore((state) => state.toggleDevMode);
  const visibleNavItems = navItems.filter((item) => !item.devOnly || devMode);

  return (
    <aside className="fixed left-0 top-0 flex h-screen w-[260px] flex-col border-r border-app-border bg-app-sidebar">
      <div className="border-b border-app-border px-6 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-app-primary text-white">
            <Bot size={20} />
          </div>
          <div>
            <h1 className="app-wordmark text-lg font-semibold leading-6 text-app-text">MindOS</h1>
            <p className="text-xs text-app-muted">Local AI Workspace</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {visibleNavItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                [
                  "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition",
                  isActive && item.primary
                    ? "bg-app-primary text-white shadow-sm shadow-violet-950/40"
                    : isActive
                      ? "bg-violet-600/15 text-violet-200 ring-1 ring-violet-500/30"
                      : item.primary
                        ? "bg-app-elevated text-app-text ring-1 ring-app-border hover:bg-app-inset"
                        : "text-app-muted hover:bg-app-elevated hover:text-app-text",
                ].join(" ")
              }
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t border-app-border px-6 py-4 text-xs text-app-muted">
        <div className="flex items-center justify-between">
          <span>version</span>
          <span className="text-app-text">v0.1-dev</span>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <span>storage</span>
          <span className="text-app-text">{storageMode ?? "sqlite"}</span>
        </div>
        <button
          type="button"
          onClick={toggleDevMode}
          className="mt-3 flex w-full items-center justify-between rounded-md border border-app-border bg-app-panel px-3 py-2 text-xs transition hover:border-app-primary/60"
          title="Toggle Developer mode"
        >
          <span>mode</span>
          <span className="flex items-center gap-2 font-medium text-app-text">
            {devMode ? "Developer" : "User"}
            <span
              className={`relative h-4 w-7 rounded-full transition ${devMode ? "bg-app-primary" : "bg-app-border"}`}
              aria-hidden="true"
            >
              <span
                className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${devMode ? "left-3.5" : "left-0.5"}`}
              />
            </span>
          </span>
        </button>
      </div>
    </aside>
  );
}
