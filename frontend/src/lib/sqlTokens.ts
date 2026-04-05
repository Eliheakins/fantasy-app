import { PLAYER_IDS_TOKEN } from "@/constants/formula";
import type { NFLPlayer } from "@/types/workbench";

export function escapeSqlLiteral(value: string): string {
  return value.replace(/'/g, "''");
}

/**
 * Replace `{{PLAYER_IDS}}` with quoted, comma-separated GSIS ids (empty pins → `''`).
 */
export function injectPinnedPlayerIds(sql: string, players: NFLPlayer[]): string {
  if (!sql.includes(PLAYER_IDS_TOKEN)) {
    return sql;
  }
  if (players.length === 0) {
    return sql.split(PLAYER_IDS_TOKEN).join("''");
  }
  const list = players.map((p) => `'${escapeSqlLiteral(p.gsis_id)}'`).join(", ");
  return sql.split(PLAYER_IDS_TOKEN).join(list);
}
