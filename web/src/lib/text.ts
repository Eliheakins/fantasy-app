/** "Eli's", "Theirs'": a name ending in s takes only the apostrophe. */
export function possessive(name: string): string {
  const n = name.trimEnd();
  if (n === "") return "";
  return /s$/i.test(n) ? `${n}'` : `${n}'s`;
}
