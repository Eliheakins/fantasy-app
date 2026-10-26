import { useTeam } from "@/lib/teamContext";

/** Wording for the team on screen: "you" for mine, the team name when another team is viewed. */
export type Who = { name: string | null; you: string; your: string };

export function whoFor(viewedName: string | null): Who {
  return viewedName === null
    ? { name: null, you: "you", your: "your" }
    : { name: viewedName, you: viewedName, your: `${viewedName}'s` };
}

export function useWho(): Who {
  return whoFor(useTeam().viewed?.team_name ?? null);
}

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
