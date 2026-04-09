import type { HubDictionaryRow } from "@/shared/lib/nlqResolveEntities";
import type { UnifiedNlqEntity } from "@/shared/lib/nlqApi";

/**
 * Convert Telescope hub dictionary rows into a unified entity payload
 * that can support both tracks (bridge_id for gold, NFL GSIS + CFB ESPN ids for PBP).
 */
export function telescopeEntitiesToUnified(rows: Array<{ bridge_id: number; display_name: string }>, dict: HubDictionaryRow[]): UnifiedNlqEntity[] {
  const nflIdByBridge = new Map<number, string | null>();
  const cfbIdByBridge = new Map<number, string | null>();
  for (const r of dict) {
    nflIdByBridge.set(r.bridge_id, r.nfl_id ?? null);
    cfbIdByBridge.set(r.bridge_id, r.cfb_id ?? null);
  }
  return rows.map((r) => ({
    display_name: r.display_name,
    bridge_id: r.bridge_id,
    nfl_gsis_id: nflIdByBridge.get(r.bridge_id) ?? null,
    cfb_espn_id: cfbIdByBridge.get(r.bridge_id) ?? null,
  }));
}

