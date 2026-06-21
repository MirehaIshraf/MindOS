import { ArrowUp } from "lucide-react";
import type { KeyboardEvent, RefObject } from "react";
import { useEffect, useRef } from "react";

type ChatInputProps = {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  useContext: boolean;
  onUseContextChange: (useContext: boolean) => void;
};

export function ChatInput({ value, onChange, onSend, disabled = false, useContext, onUseContextChange }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useAutoGrow(textareaRef, value);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSend();
    }
  }

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div className="rounded-lg border border-app-border bg-app-panel p-3 shadow-lg shadow-black/20">
      <div className="flex items-end gap-3">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask MindOS anything about your work..."
          rows={1}
          className="max-h-32 min-h-11 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-app-text outline-none placeholder:text-app-muted"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={!canSend}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-app-primary text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:bg-app-elevated disabled:text-app-muted"
          aria-label="Send message"
        >
          <ArrowUp size={18} />
        </button>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 px-2 text-xs text-app-muted">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={useContext}
            onChange={(event) => onUseContextChange(event.target.checked)}
            className="h-3.5 w-3.5 accent-violet-600"
          />
          Use local memory
        </label>
        <span>Keyword retrieval is connected. Semantic memory coming soon.</span>
      </div>
    </div>
  );
}

function useAutoGrow(textareaRef: RefObject<HTMLTextAreaElement>, value: string) {
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 128)}px`;
  }, [textareaRef, value]);
}
