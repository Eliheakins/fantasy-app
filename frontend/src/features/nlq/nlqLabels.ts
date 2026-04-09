import type { UnifiedNlqResponse } from "@/shared/lib/nlqApi";

export function humanizeRoutedTrack(track: UnifiedNlqResponse["track"]): string {
  switch (track) {
    case "telescope":
      return "Season summaries (gold_unified_performance — NFL & CFB)";
    case "microscope_nfl":
      return "NFL play-by-play (nfl_pbp_all)";
    case "microscope_cfb":
      return "College play-by-play (cfb_pbp_all)";
    default:
      return track;
  }
}
