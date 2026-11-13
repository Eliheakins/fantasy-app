import { useLocation } from "react-router-dom";
import { ManifestProvider } from "@/stat/react/manifest";
import { QueryBuilderPanel } from "@/features/explore/QueryBuilderPanel";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PlayersNav } from "@/features/players/PlayersNav";

/** Stat explorer: queries run in the browser on the shards the server serves at /api/stat/data. */
export default function Explore() {
  const here = useLocation();
  return (
    <TooltipProvider>
      <PlayersNav here={here} />
      <ManifestProvider>
        <QueryBuilderPanel />
      </ManifestProvider>
    </TooltipProvider>
  );
}
