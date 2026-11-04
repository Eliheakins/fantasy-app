import { Input } from "@/shared/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/shared/components/ui/toggle-group";
import { getStatById } from "@/shared/config/statDictionary";
import { MAX_LIMIT } from "@/shared/lib/queryUrl";
import { useQueryState } from "@/shared/lib/useQueryState";

const NO_RANKING = "none";

/**
 * Orders the rows by one selected stat and keeps the first N. With no player pinned this is a
 * league leaderboard; with players pinned it sorts them.
 */
export function RankingControl() {
  const { state, setRanking } = useQueryState();
  const { order, limit, stats } = state;

  const commitRows = (text: string) => {
    if (order && text.trim() !== "") {
      setRanking(order, Number(text));
    }
  };

  return (
    <div className="space-y-1">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Ranking</h3>
      <p className="mt-0.5 text-xs text-ink-muted">
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
            {getStatById(id)?.label ?? id}
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
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            Rows
            <Input
              // Re-mounts when the URL's limit changes, so the box always starts from it.
              key={limit ?? "none"}
              type="number"
              min={1}
              max={MAX_LIMIT}
              defaultValue={limit ?? undefined}
              onBlur={(e) => commitRows(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  commitRows(e.currentTarget.value);
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
