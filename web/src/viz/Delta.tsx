import { cn } from "@/lib/utils";
import { type ConfidenceLevel, formatDelta } from "./format";

const TONE_CLASS = {
  positive: "text-positive",
  negative: "text-negative",
  neutral: "text-mark-muted",
} as const;

type DeltaProps = {
  points: number;
  /** A toss-up change never gets a green or red arrow. */
  confidence?: ConfidenceLevel;
  className?: string;
};

/** The only place green and red appear. The sign and arrow carry the meaning; colour repeats it. */
export function Delta({ points, confidence, className }: DeltaProps) {
  const { text, tone } = formatDelta(points);
  const shown = confidence === "toss-up" ? "neutral" : tone;
  return (
    <span className={cn("tabular-nums whitespace-nowrap", TONE_CLASS[shown], className)}>
      {text}
    </span>
  );
}
