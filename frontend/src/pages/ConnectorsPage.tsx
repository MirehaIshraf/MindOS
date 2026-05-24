import { Cable } from "lucide-react";

import { Card } from "../components/shared/Card";
import { EmptyState } from "../components/shared/EmptyState";

export function ConnectorsPage() {
  return (
    <Card>
      <EmptyState
        icon={<Cable size={36} />}
        title="Connectors"
        description="Manage future data connectors such as file watcher, VSCode, browser, GitHub, Jira, logs, and email."
      />
    </Card>
  );
}
