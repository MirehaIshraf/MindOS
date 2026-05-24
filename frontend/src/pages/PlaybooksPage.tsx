import { Workflow } from "lucide-react";

import { Card } from "../components/shared/Card";
import { EmptyState } from "../components/shared/EmptyState";

export function PlaybooksPage() {
  return (
    <Card>
      <EmptyState
        icon={<Workflow size={36} />}
        title="Playbooks"
        description="Create and manage reusable workflows. Playbook implementation will be added later."
      />
    </Card>
  );
}
