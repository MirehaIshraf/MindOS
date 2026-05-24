import { create } from "zustand";

type AppState = {
  sidebarOpen: boolean;
  backendOnline: boolean;
  storageMode: string | null;
  activePageTitle: string;
  setSidebarOpen: (open: boolean) => void;
  setBackendOnline: (online: boolean) => void;
  setStorageMode: (mode: string | null) => void;
  setActivePageTitle: (title: string) => void;
};

export const useAppStore = create<AppState>((set) => ({
  sidebarOpen: true,
  backendOnline: false,
  storageMode: null,
  activePageTitle: "Chat",
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setBackendOnline: (backendOnline) => set({ backendOnline }),
  setStorageMode: (storageMode) => set({ storageMode }),
  setActivePageTitle: (activePageTitle) => set({ activePageTitle }),
}));
