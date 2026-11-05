import { cn } from "@/lib/utils";

export interface CollapsibleCodeProps {
  title: string;
  code: string;
  className?: string;
  preClassName?: string;
  maxHeightClass?: string;
}

export function CollapsibleCode({
  title,
  code,
  className,
  preClassName,
  maxHeightClass = "max-h-40",
}: CollapsibleCodeProps) {
  return (
    <details className={cn("text-caption text-muted", className)}>
      <summary className="cursor-pointer hover:text-ink">{title}</summary>
      <pre
        className={cn(
          "mt-2 overflow-auto whitespace-pre-wrap rounded border border-line bg-panel p-2 font-mono text-[11px] text-muted",
          maxHeightClass,
          preClassName,
        )}
      >
        {code}
      </pre>
    </details>
  );
}
