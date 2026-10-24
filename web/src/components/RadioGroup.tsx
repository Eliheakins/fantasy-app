import { type KeyboardEvent, useRef } from "react";
import { cn } from "@/lib/utils";

type Option<K extends string> = { key: K; label: string };

type Props<K extends string> = {
  label: string;
  options: readonly Option<K>[];
  value: K;
  onChange: (key: K) => void;
  className?: string;
  optionClassName?: (selected: boolean) => string;
};

/** ARIA radio group: one tab stop (the selected radio), arrow keys move and select. */
export function RadioGroup<K extends string>({ label, options, value, onChange, className, optionClassName }: Props<K>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (from: number, step: number) => {
    const next = (from + step + options.length) % options.length;
    const target = options[next];
    if (!target) return;
    onChange(target.key);
    refs.current[next]?.focus();
  };
  const onKeyDown = (e: KeyboardEvent, i: number) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") move(i, 1);
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") move(i, -1);
    else return;
    e.preventDefault();
  };
  return (
    <div role="radiogroup" aria-label={label} className={className}>
      {options.map((o, i) => (
        <button
          key={o.key}
          ref={(el) => { refs.current[i] = el; }}
          type="button"
          role="radio"
          aria-checked={o.key === value}
          tabIndex={o.key === value ? 0 : -1}
          onClick={() => onChange(o.key)}
          onKeyDown={(e) => onKeyDown(e, i)}
          className={cn("min-h-[44px]", optionClassName?.(o.key === value))}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
