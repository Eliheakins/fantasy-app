import { Callout } from "@/shared/components/Callout";
import { CollapsibleCode } from "@/shared/components/CollapsibleCode";
import { QueryResultTable } from "@/shared/components/QueryResultTable";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardTitle } from "@/shared/components/ui/card";
import { Textarea } from "@/shared/components/ui/textarea";
import { NlqEntityChips } from "@/features/nlq/NlqEntityChips";
import { humanizeRoutedTrack } from "@/features/nlq/nlqLabels";
import { useUnifiedNlqAsk } from "@/features/nlq/useUnifiedNlqAsk";

export function NLQPanel() {
  const nlq = useUnifiedNlqAsk();

  return (
    <Card className="overflow-hidden border-border">
      <CardContent className="space-y-4 px-4 pb-6 pt-5 md:px-6">
        <div>
          <CardTitle className="text-lg text-ink">Ask (NLQ)</CardTitle>
          <p className="mt-1 text-xs text-ink-muted">
            Natural language → SQL. Routing is automatic (season stats vs. NFL or college play-by-play). Player names are
            matched locally from the hub dictionary before the model runs.
          </p>
        </div>

        {nlq.routedTrack ? (
          <Callout variant="info" className="text-xs">
            <span className="font-medium text-ink">Data layer:</span>{" "}
            <span>{humanizeRoutedTrack(nlq.routedTrack)}</span>
            <span className="ml-2 font-mono text-[10px] text-ink-muted/80">({nlq.routedTrack})</span>
          </Callout>
        ) : null}

        <Textarea
          value={nlq.question}
          onChange={(e) => nlq.setQuestion(e.target.value)}
          placeholder="e.g. Travis Kelce average EPA per play in 2023, or top 5 WR by YPRR"
          className="min-h-[88px] text-sm"
          disabled={nlq.running}
          aria-label="Natural language question"
        />

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" onClick={() => void nlq.onAsk()} disabled={nlq.running}>
            {nlq.running ? "Working…" : "Ask"}
          </Button>
        </div>

        <NlqEntityChips entities={nlq.resolvedUnified} />

        {nlq.userMessage ? <Callout variant="danger">{nlq.userMessage}</Callout> : null}

        {nlq.techDetail ? (
          <CollapsibleCode title="Technical detail" code={nlq.techDetail} maxHeightClass="max-h-32" />
        ) : null}

        {nlq.result && nlq.result.rows.length > 0 ? (
          <div className="space-y-1">
            <p className="text-xs font-medium text-ink-muted">
              Results{" "}
              <span className="font-normal">
                ({nlq.result.rows.length} row{nlq.result.rows.length === 1 ? "" : "s"})
              </span>
            </p>
            <QueryResultTable result={nlq.result} zebra />
          </div>
        ) : null}

        {nlq.result && nlq.result.rows.length === 0 && !nlq.userMessage ? (
          <p className="text-sm text-ink-muted">Query returned no rows.</p>
        ) : null}

        {nlq.generatedSql ? <CollapsibleCode title="Generated SQL" code={nlq.generatedSql} /> : null}
      </CardContent>
    </Card>
  );
}
