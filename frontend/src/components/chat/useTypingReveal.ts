import { useEffect, useRef, useState } from "react";

const WORD_INTERVAL_MS = 28;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

type TypingReveal = {
  displayText: string;
  done: boolean;
};

/**
 * Progressively reveals `text` word-by-word when `enabled` is true (a simulated
 * "typing" effect over an already-complete reply). When disabled — or when the
 * user prefers reduced motion — the full text is returned immediately.
 *
 * `onTick` fires on each reveal step (used to keep the view scrolled to bottom).
 * It runs once per text value; re-renders with the same text do not restart it.
 */
export function useTypingReveal(text: string, enabled: boolean, onTick?: () => void): TypingReveal {
  // -1 is a sentinel meaning "show the full text".
  const [revealedCount, setRevealedCount] = useState<number>(-1);
  const tokensRef = useRef<string[]>([]);
  const onTickRef = useRef<typeof onTick>(onTick);
  onTickRef.current = onTick;

  useEffect(() => {
    if (!enabled || !text || prefersReducedMotion()) {
      setRevealedCount(-1);
      return;
    }
    // Split keeping whitespace as its own tokens so spacing is preserved.
    const tokens = text.split(/(\s+)/);
    tokensRef.current = tokens;
    setRevealedCount(0);
    let index = 0;
    const intervalId = window.setInterval(() => {
      index += 1;
      setRevealedCount(index);
      onTickRef.current?.();
      if (index >= tokens.length) {
        window.clearInterval(intervalId);
      }
    }, WORD_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
    // Intentionally only re-run when the text or enabled flag changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, enabled]);

  if (revealedCount < 0) {
    return { displayText: text, done: true };
  }
  const tokens = tokensRef.current;
  const done = revealedCount >= tokens.length;
  return {
    displayText: done ? text : tokens.slice(0, revealedCount).join(""),
    done,
  };
}
