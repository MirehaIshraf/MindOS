import type { InputHTMLAttributes } from "react";

type InputProps = InputHTMLAttributes<HTMLInputElement>;

export function Input({ className = "", ...props }: InputProps) {
  return (
    <input
      className={`h-10 w-full rounded-md border border-app-border bg-app-inset px-3 text-sm text-app-text outline-none transition placeholder:text-app-muted focus:border-app-primary focus:ring-2 focus:ring-violet-900/50 ${className}`}
      {...props}
    />
  );
}
