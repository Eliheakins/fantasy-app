import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { getStatById } from "@/stat/config/statDictionary";
import { clampLimit, MAX_LIMIT } from "@/stat/lib/queryUrl";
import { useQueryState } from "@/stat/react/useQueryState";

const NO_RANKING = "none";

/**
 * Orders the rows by one selected stat and keeps the first N. With no player pinned this is a
 * league leaderboard; with players pinned it sorts them.
 */
export function RankingControl() {
  const { state, setRanking } = useQueryState();
  const { order, limit, stats } = state;

  // Shows the rows actually kept, since the URL clamps what was typed (250 becomes 100).
  const commitRows = (box: HTMLInputElement) => {
    if (order && box.value.trim() !== "") {
      const rows = clampLimit(Number(box.value));
      box.value = String(rows);
      setRanking(order, rows);
    }
  };
  // Several stats share a label (WPA, YAC share %); the player role tells them apart.
  const labelOf = (id: string) => {
    const stat = getStatById(id);
    const label = stat?.label ?? id;
    const shared = stats.some((other) => other !== id && getStatById(other)?.label === label);
    return shared && stat ? `${label} (${stat.playerRole})` : label;
  };

  return (
    <div className="space-y-1">
      <h3 className="text-caption font-semibold uppercase tracking-wide text-focus">Ranking</h3>
      <p className="mt-0.5 text-caption text-muted">
        Order by one stat and keep the first rows. With no player pinned, it ranks everyone who has the stat.
      </p>
      <ToggleGroup
        type="single"
        value={order?.metric ?? NO_RANKING}
        onValueChange={(metric) => {
          if (!metric) {
            return;
          }
          setRanking(metric === NO_RANKING ? null : { metric, direction: order?.direction ?? "desc" });
        }}
        className="mt-3 flex flex-wrap gap-2"
        aria-label="Rank by"
      >
        <ToggleGroupItem value={NO_RANKING} className="rounded-md">
          No ranking
        </ToggleGroupItem>
        {stats.map((id) => (
          <ToggleGroupItem key={id} value={id} className="rounded-md">
            {labelOf(id)}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {order ? (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <ToggleGroup
            type="single"
            value={order.direction}
            onValueChange={(direction) => {
              if (direction === "asc" || direction === "desc") {
                setRanking({ ...order, direction });
              }
            }}
            className="flex gap-2"
            aria-label="Ranking direction"
          >
            <ToggleGroupItem value="desc" className="rounded-md">
              Highest first
            </ToggleGroupItem>
            <ToggleGroupItem value="asc" className="rounded-md">
              Lowest first
            </ToggleGroupItem>
          </ToggleGroup>
          <label className="flex items-center gap-2 text-caption text-muted">
            Rows
            <Input
              // Re-mounts when the URL's limit changes, so the box always starts from it.
              key={limit ?? "none"}
              type="number"
              min={1}
              max={MAX_LIMIT}
              defaultValue={limit ?? undefined}
              onBlur={(e) => commitRows(e.currentTarget)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  commitRows(e.currentTarget);
                }
              }}
              className="w-20"
              aria-label="Rows to show"
            />
          </label>
        </div>
      ) : null}
    </div>
  );
}
