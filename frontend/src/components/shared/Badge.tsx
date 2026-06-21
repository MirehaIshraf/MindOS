import type { ReactNode } from "react";

type BadgeVariant = "default" | "success" | "warning" | "danger" | "info";

type BadgeProps = {
  variant?: BadgeVariant;
  children: ReactNode;
};

const variants: Record<BadgeVariant, string> = {
  default: "border-app-border bg-app-elevated text-app-muted",
  success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  warning: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  danger: "border-red-500/30 bg-red-500/10 text-red-300",
  info: "border-violet-500/30 bg-violet-500/10 text-violet-300",
};

export function Badge({ variant = "default", children }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${variants[variant]}`}>
      {children}
    </span>
  );
}
