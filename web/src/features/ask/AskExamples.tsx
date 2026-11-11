import { Button } from "@/components/ui/button";

/** One example per thing Ask can answer: a stat, a ranking, a free-agent ranking, start or sit, a trade, a waiver question, a player outlook. */
const EXAMPLE_QUESTIONS = [
  "Mahomes passing yards and touchdowns this season",
  "Most receiving yards this season",
  "Free agent WRs with the most targets over the last 3 games",
  "Start Kelce or Kittle",
  "Trade Kelce for Kittle",
  "Who should I pick up on waivers",
  "Travis Kelce rest of season projection",
] as const;

/** Example chips and a note on how Ask reads a question. Picking a chip asks it at once. */
export function AskExamples({ onPick, disabled }: { onPick: (question: string) => void; disabled: boolean }) {
  return (
    <div className="space-y-2">
      <ul className="flex flex-wrap gap-2" aria-label="Example questions">
        {EXAMPLE_QUESTIONS.map((q) => (
          <li key={q}>
            <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => onPick(q)}>
              {q}
            </Button>
          </li>
        ))}
      </ul>
      <details className="measure text-caption text-muted">
        <summary className="cursor-pointer">How Ask reads a question</summary>
        <p className="mt-1">
          Names are matched in your browser. Built-in rules read what they can; the hosted model (Jev) reads the rest, with a local model as
          the fallback. The model sees only the question. The numbers are computed in your browser from play-by-play data.
        </p>
      </details>
    </div>
  );
}
