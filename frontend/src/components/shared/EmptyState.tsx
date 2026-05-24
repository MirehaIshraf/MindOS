import type { ReactNode } from "react";

type EmptyStateProps = {
  icon?: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
};

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex min-h-[280px] flex-col items-center justify-center rounded-md border border-dashed border-app-border px-8 py-12 text-center">
      {icon ? <div className="mb-5 text-app-primary">{icon}</div> : null}
      <h2 className="text-xl font-semibold text-app-text">{title}</h2>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-app-muted">{description}</p>
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  );
}
