import { cn } from "@/lib/utils";
import { type ConfidenceLevel, confidenceFromShare } from "./format";

const LEVEL_CLASS: Record<ConfidenceLevel, string> = {
  clear: "font-semibold text-text",
  lean: "text-text",
  "toss-up": "italic text-mark-muted",
};

type ConfidenceProps = ({ level: ConfidenceLevel } | { share: number }) & { className?: string };

/** One word for "how often is this actually better": clear, lean or toss-up. Never coloured. */
export function Confidence(props: ConfidenceProps) {
  const level = "level" in props ? props.level : confidenceFromShare(props.share);
  return <span className={cn("text-caption", LEVEL_CLASS[level], props.className)}>{level}</span>;
}
