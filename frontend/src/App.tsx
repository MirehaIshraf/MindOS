import { Navigate, Route, Routes } from "react-router-dom";

import { Sidebar } from "./components/layout/Sidebar";
import { TopBar } from "./components/layout/TopBar";
import { ChatPage } from "./pages/ChatPage";
import { ConnectorsPage } from "./pages/ConnectorsPage";
import { DevPage } from "./pages/DevPage";
import { MemoryPage } from "./pages/MemoryPage";
import { PlaybooksPage } from "./pages/PlaybooksPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TasksPage } from "./pages/TasksPage";

export default function App() {
  return (
    <div className="min-h-screen bg-app-background text-app-text">
      <Sidebar />
      <TopBar />
      <main className="ml-[260px] min-h-screen pt-16">
        <div className="mx-auto max-w-6xl px-8 py-8">
          <Routes>
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/memory" element={<MemoryPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/connectors" element={<ConnectorsPage />} />
            <Route path="/playbooks" element={<PlaybooksPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/dev" element={<DevPage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
