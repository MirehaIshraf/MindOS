import { create } from "zustand";

export type Theme = "dark" | "light";

const THEME_STORAGE_KEY = "mindos.theme";

export function readStoredTheme(): Theme {
  if (typeof window === "undefined") {
    return "dark";
  }
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === "light" ? "light" : "dark";
}

export function applyTheme(theme: Theme) {
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", theme);
  }
}

type AppState = {
  sidebarOpen: boolean;
  backendOnline: boolean;
  storageMode: string | null;
  activePageTitle: string;
  theme: Theme;
  setSidebarOpen: (open: boolean) => void;
  setBackendOnline: (online: boolean) => void;
  setStorageMode: (mode: string | null) => void;
  setActivePageTitle: (title: string) => void;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
};

function persistTheme(theme: Theme) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }
  applyTheme(theme);
}

export const useAppStore = create<AppState>((set, get) => ({
  sidebarOpen: true,
  backendOnline: false,
  storageMode: null,
  activePageTitle: "Chat",
  theme: readStoredTheme(),
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setBackendOnline: (backendOnline) => set({ backendOnline }),
  setStorageMode: (storageMode) => set({ storageMode }),
  setActivePageTitle: (activePageTitle) => set({ activePageTitle }),
  setTheme: (theme) => {
    persistTheme(theme);
    set({ theme });
  },
  toggleTheme: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    persistTheme(next);
    set({ theme: next });
  },
}));
