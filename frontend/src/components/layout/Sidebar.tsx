import {
  Bot,
  Cable,
  Code2,
  Database,
  ListTodo,
  MessageSquare,
  Settings,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAppStore } from "../../store/appStore";

const navItems = [
  { label: "Chat", path: "/chat", icon: MessageSquare, primary: true },
  { label: "Memory", path: "/memory", icon: Database },
  { label: "Tasks", path: "/tasks", icon: ListTodo },
  { label: "Connectors", path: "/connectors", icon: Cable },
  { label: "Settings", path: "/settings", icon: Settings },
  { label: "Dev", path: "/dev", icon: Code2 },
];

export function Sidebar() {
  const storageMode = useAppStore((state) => state.storageMode);

  return (
    <aside className="fixed left-0 top-0 flex h-screen w-[260px] flex-col border-r border-app-border bg-app-sidebar">
      <div className="border-b border-app-border px-6 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-app-primary text-white">
            <Bot size={20} />
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-6 text-app-text">MindOS</h1>
            <p className="text-xs text-app-muted">Local AI Workspace</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
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
                        ? "bg-zinc-900 text-app-text ring-1 ring-app-border hover:bg-zinc-800"
                        : "text-app-muted hover:bg-zinc-800 hover:text-app-text",
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
        <div className="mt-2 flex items-center justify-between">
          <span>mode</span>
          <span className="text-app-text">development</span>
        </div>
      </div>
    </aside>
  );
}
