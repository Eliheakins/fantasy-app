/** Static text chip for a playoff matchup ("Round 1", "Bye", "Eliminated", "Champion"); nothing in the regular season. */
export function PlayoffLabel({ label }: { label: string | null | undefined }) {
  if (!label) return null;
  return <span className="inline-block rounded-full bg-panel px-2 py-0.5 text-caption font-semibold text-ink">{label}</span>;
}
