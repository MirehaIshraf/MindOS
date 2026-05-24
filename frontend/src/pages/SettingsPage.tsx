import { Settings } from "lucide-react";

import { Card } from "../components/shared/Card";
import { EmptyState } from "../components/shared/EmptyState";

export function SettingsPage() {
  return (
    <Card>
      <EmptyState
        icon={<Settings size={36} />}
        title="Settings"
        description="Configure local models, storage, privacy, and installer-related settings later."
      />
    </Card>
  );
}
