import { AlertTriangle } from "lucide-react";

import { Badge } from "../shared/Badge";

type TaskPreviewDetailsProps = {
  taskType: string;
  preview: Record<string, unknown> | null | undefined;
  result?: Record<string, unknown> | null;
  sourcesUsed?: Array<Record<string, unknown>>;
  compact?: boolean;
};

const writeLikeTasks = new Set(["create_jira_ticket", "draft_email", "create_pull_request"]);

const handledPreviewKeys = new Set([
  "title",
  "description",
  "priority",
  "recipient",
  "subject",
  "body",
  "repo",
  "branch_name",
  "commit_message",
  "pr_title",
  "pr_body",
  "report_markdown",
  "context_summary",
  "confidence",
  "evidence",
  "missing_fields",
  "safety_notes",
  "planner_model",
  "planner_provider",
  "planner_warning",
  "context_stats",
]);

export function TaskPreviewDetails({ taskType, preview, result, sourcesUsed = [], compact = false }: TaskPreviewDetailsProps) {
  const previewData = asRecord(preview);
  const evidence = evidenceItems(previewData.evidence).length > 0 ? evidenceItems(previewData.evidence) : evidenceItems(sourcesUsed);
  const missing = stringItems(previewData.missing_fields);
  const safetyNotes = stringItems(previewData.safety_notes);
  const notes = safetyNotes.length > 0 ? safetyNotes : writeLikeTasks.has(taskType) ? ["This action requires confirmation. Current execution is mock-only."] : [];

  return (
    <div className={`space-y-4 ${compact ? "mt-3" : "mt-4"}`}>
      {renderTaskSpecificPreview(taskType, previewData)}
      {textField(previewData.context_summary) ? <PlainSection title="Context Summary" value={textField(previewData.context_summary)} /> : null}
      {evidence.length > 0 ? <EvidenceSection items={evidence} /> : null}
      {missing.length > 0 ? <MissingFieldsSection items={missing} /> : null}
      {notes.length > 0 ? <SafetyNotesSection items={notes} /> : null}
      {Object.keys(fallbackFields(previewData)).length > 0 ? <KeyValueSection title="Additional Preview Details" value={fallbackFields(previewData)} /> : null}
      {result && Object.keys(result).length > 0 ? <KeyValueSection title="Mock Result" value={result} /> : null}
    </div>
  );
}

function renderTaskSpecificPreview(taskType: string, preview: Record<string, unknown>) {
  if (taskType === "draft_email") {
    return (
      <PreviewSection
        title="Email Preview"
        rows={[
          ["Recipient", textField(preview.recipient) || "Missing"],
          ["Subject", textField(preview.subject)],
          ["Body", textField(preview.body)],
        ]}
      />
    );
  }

  if (taskType === "create_jira_ticket") {
    return (
      <PreviewSection
        title="Jira Ticket Preview"
        rows={[
          ["Title", textField(preview.title)],
          ["Priority", textField(preview.priority)],
          ["Description", textField(preview.description)],
        ]}
      />
    );
  }

  if (taskType === "create_pull_request") {
    return (
      <PreviewSection
        title="Pull Request Preview"
        rows={[
          ["Repo", textField(preview.repo) || "Missing"],
          ["Branch", textField(preview.branch_name)],
          ["PR Title", textField(preview.pr_title)],
          ["PR Body", textField(preview.pr_body)],
        ]}
      />
    );
  }

  if (taskType === "suggest_branch_name") {
    return <PreviewSection title="Branch Suggestion" rows={[["Branch Name", textField(preview.branch_name)]]} />;
  }

  if (taskType === "generate_commit_message") {
    return <PreviewSection title="Commit Message" rows={[["Commit Message", textField(preview.commit_message)]]} />;
  }

  if (taskType === "weekly_report") {
    return <PlainSection title="Weekly Report" value={textField(preview.report_markdown) || textField(preview.description)} />;
  }

  return null;
}

function PreviewSection({ title, rows }: { title: string; rows: Array<[string, string]> }) {
  const visibleRows = rows.filter(([, value]) => value);
  if (visibleRows.length === 0) {
    return null;
  }

  return (
    <section className="rounded-md border border-app-border bg-zinc-950 p-3">
      <p className="text-xs font-medium uppercase text-app-muted">{title}</p>
      <div className="mt-3 space-y-3">
        {visibleRows.map(([label, value]) => (
          <div key={label}>
            <p className="text-xs text-app-muted">{label}</p>
            <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-app-text">{value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function PlainSection({ title, value }: { title: string; value: string }) {
  if (!value) {
    return null;
  }
  return (
    <section className="rounded-md border border-app-border bg-zinc-950 p-3">
      <p className="text-xs font-medium uppercase text-app-muted">{title}</p>
      <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-app-text">{value}</div>
    </section>
  );
}

function EvidenceSection({ items }: { items: EvidenceItem[] }) {
  return (
    <section className="rounded-md border border-app-border bg-zinc-950 p-3">
      <p className="text-xs font-medium uppercase text-app-muted">Evidence from Memory</p>
      <div className="mt-3 space-y-2">
        {items.map((item, index) => (
          <div key={`${item.title}-${index}`} className="rounded-md border border-app-border/70 bg-zinc-900/70 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">{item.source || "memory"}</Badge>
              <p className="text-sm font-medium text-app-text">{item.title || "Memory item"}</p>
            </div>
            {item.reason ? <p className="mt-2 text-sm leading-6 text-app-muted">{item.reason}</p> : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function MissingFieldsSection({ items }: { items: string[] }) {
  return (
    <section className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
      <div className="flex items-center gap-2 text-amber-100">
        <AlertTriangle size={16} />
        <p className="text-xs font-medium uppercase">Missing Fields</p>
      </div>
      <ul className="mt-2 space-y-1 text-sm leading-6 text-amber-100">
        {items.map((item) => (
          <li key={item}>- {missingFieldMessage(item)}</li>
        ))}
      </ul>
    </section>
  );
}

function SafetyNotesSection({ items }: { items: string[] }) {
  return (
    <section className="rounded-md border border-violet-500/30 bg-violet-500/10 p-3">
      <p className="text-xs font-medium uppercase text-violet-200">Safety Notes</p>
      <ul className="mt-2 space-y-1 text-sm leading-6 text-violet-100">
        {items.map((item, index) => (
          <li key={`${item}-${index}`}>- {item}</li>
        ))}
      </ul>
    </section>
  );
}

function KeyValueSection({ title, value }: { title: string; value: Record<string, unknown> }) {
  const entries = Object.entries(value);
  if (entries.length === 0) {
    return null;
  }
  return (
    <section className="rounded-md border border-app-border bg-zinc-950 p-3">
      <p className="text-xs font-medium uppercase text-app-muted">{title}</p>
      <div className="mt-3 grid gap-3">
        {entries.map(([key, item]) => (
          <div key={key}>
            <p className="text-xs text-app-muted">{labelize(key)}</p>
            <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-app-text">{displayValue(item)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

type EvidenceItem = {
  source: string;
  title: string;
  reason: string;
};

function evidenceItems(value: unknown): EvidenceItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => {
      if (typeof item === "string") {
        return { source: "memory", title: item, reason: "" };
      }
      const record = asRecord(item);
      if (!record) {
        return null;
      }
      return {
        source: textField(record.source) || "memory",
        title: textField(record.title) || textField(record.name) || "Memory item",
        reason: textField(record.reason) || textField(record.match_reason),
      };
    })
    .filter((item): item is EvidenceItem => item !== null);
}

function stringItems(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter((item) => item.trim()) : [];
}

function fallbackFields(preview: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(preview).filter(([key, value]) => !handledPreviewKeys.has(key) && value !== null && value !== undefined && value !== ""));
}

function missingFieldMessage(field: string) {
  if (field === "recipient") {
    return "Recipient is missing. You can still confirm mock draft, but real sending later will require a recipient.";
  }
  if (field === "repo") {
    return "Repository is missing. You can still confirm the mock preview, but a real action later will require a repository.";
  }
  return `${labelize(field)} is missing. You can still confirm mock execution, but real execution later may require it.`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function textField(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function displayValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value, null, 2);
}

function labelize(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}
