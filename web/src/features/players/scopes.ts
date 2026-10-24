export type Scope = "mine" | "league" | "free";

export const SCOPES: readonly { key: Scope; label: string }[] = [
  { key: "mine", label: "My roster" },
  { key: "league", label: "Other rosters" },
  { key: "free", label: "Free agents" },
];
