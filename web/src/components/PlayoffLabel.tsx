/** Static chip showing the server's `playoff_label` text as is ("Round 2 vs X", "Bye this round", "Eliminated", "Champion", "Consolation game vs X"); nothing when there is none. */
export function PlayoffLabel({ label }: { label: string | null | undefined }) {
  if (!label) return null;
  return <span className="inline-block rounded-full bg-panel px-2 py-0.5 text-caption font-semibold text-ink">{label}</span>;
}
