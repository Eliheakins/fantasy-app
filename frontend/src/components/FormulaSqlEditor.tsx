import { Fragment, useCallback, useRef, type ReactNode } from "react";

import { PLAYER_IDS_TOKEN } from "@/constants/formula";
import { cn } from "@/lib/utils";

interface FormulaSqlEditorProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
}

/**
 * Monospace editor with the `{{PLAYER_IDS}}` token highlighted (textarea + mirrored overlay).
 */
export function FormulaSqlEditor({ value, onChange, className, placeholder }: FormulaSqlEditorProps) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);

  const syncScroll = useCallback(() => {
    const ta = taRef.current;
    const mirror = mirrorRef.current;
    if (!ta || !mirror) {
      return;
    }
    mirror.scrollTop = ta.scrollTop;
    mirror.scrollLeft = ta.scrollLeft;
  }, []);

  return (
    <div className={cn("relative min-h-[140px] w-full rounded-md border border-border bg-input", className)}>
      <div
        ref={mirrorRef}
        className={cn(
          "pointer-events-none absolute inset-0 z-0 overflow-auto whitespace-pre-wrap break-words p-3",
          "font-mono text-sm leading-normal text-ink",
        )}
        aria-hidden
      >
        {highlightToken(value, PLAYER_IDS_TOKEN)}
      </div>
      <textarea
        ref={taRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={syncScroll}
        spellCheck={false}
        placeholder={placeholder}
        className={cn(
          "relative z-10 min-h-[140px] w-full resize-y bg-transparent p-3 font-mono text-sm leading-normal",
          "text-transparent caret-ink placeholder:text-ink-muted",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        )}
        style={{ WebkitTextFillColor: "transparent" }}
      />
    </div>
  );
}

function highlightToken(text: string, token: string) {
  if (!text) {
    return null;
  }
  const parts = text.split(token);
  if (parts.length === 1) {
    return <span className="text-ink">{text}</span>;
  }
  const nodes: ReactNode[] = [];
  parts.forEach((part, i) => {
    nodes.push(<span key={`t-${i}`} className="text-ink">{part}</span>);
    if (i < parts.length - 1) {
      nodes.push(
        <span
          key={`k-${i}`}
          className="rounded bg-accent-subtle px-0.5 font-semibold text-accent ring-1 ring-accent/30"
        >
          {token}
        </span>,
      );
    }
  });
  return <Fragment>{nodes}</Fragment>;
}
