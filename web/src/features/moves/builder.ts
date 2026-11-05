import { formatValue, points, sideMeasures } from "@/features/trades/logic";
import type { TradeEvaluation } from "@/features/trades/types";
import { NOISE_PERCENT } from "@/viz";

export const BUILDER_DEBOUNCE_MS = 600;

const sides = (r: TradeEvaluation) => ({ me: r.odds.find((s) => s.side === "me"), them: r.odds.find((s) => s.side === "them") });
const playoffChange = (s: TradeEvaluation["odds"][number]) => points(s.playoff_after - s.playoff_before);

/** A pitch makes sense only when both teams' playoff odds rise by more than the noise bar. */
export function canPitch(r: TradeEvaluation): boolean {
  const { me, them } = sides(r);
  return !!me && !!them && playoffChange(me) > NOISE_PERCENT && playoffChange(them) > NOISE_PERCENT;
}

const range = (s: TradeEvaluation["odds"][number]) => {
  const m = sideMeasures(s)[0];
  return `${formatValue(m.before, true)} to ${formatValue(m.after, true)}`;
};

/** Message text from the numbers alone; nothing is sent anywhere. Call only when canPitch is true. */
export function pitchText(r: TradeEvaluation, give: readonly string[], get: readonly string[]): string {
  const { me, them } = sides(r);
  if (!me || !them) return "";
  return [
    `Hi, would you do my ${give.join(" and ")} for your ${get.join(" and ")}?`,
    `By my simulations it helps both of us: your playoff odds go ${range(them)}, and mine go ${range(me)}.`,
    "Let me know what you think.",
  ].join(" ");
}

/** Clipboard API first, then a hidden textarea and execCommand; true when the text was copied. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // clipboard missing or refused (insecure page, no permission): use the fallback
  }
  const box = document.createElement("textarea");
  box.value = text;
  box.setAttribute("readonly", "");
  box.style.position = "fixed";
  box.style.opacity = "0";
  document.body.appendChild(box);
  box.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    box.remove();
  }
}
