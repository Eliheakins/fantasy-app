import type { Dispatch, SetStateAction } from "react";
import { useCallback, useState } from "react";

import { mountNlqMicroscopeTrack } from "@/features/nlq/mountNlqMicroscope";
import { goldUnifiedParquetUrl, playerHubParquetUrl } from "@/shared/lib/api";
import { runQuery } from "@/shared/lib/duckdb";
import { requestUnifiedNlq, type UnifiedNlqEntity } from "@/shared/lib/nlqApi";
import { fetchHubDictionary, resolveNlqEntities } from "@/shared/lib/nlqResolveEntities";
import { ensureGoldTelescopeMounted } from "@/shared/lib/workbenchDuckdb";
import { telescopeEntitiesToUnified } from "@/features/nlq/common/unifiedEntities";
import type { QueryResult } from "@/shared/types/workbench";

const NLQ_USER_ERROR =
  "I couldn't quite build that query. Try rephrasing with specific player names and seasons.";

type TrackState = {
  setResolvedUnified: Dispatch<SetStateAction<UnifiedNlqEntity[]>>;
  setGeneratedSql: Dispatch<SetStateAction<string | null>>;
  setUserMessage: Dispatch<SetStateAction<string | null>>;
  setTechDetail: Dispatch<SetStateAction<string | null>>;
};

export function useUnifiedNlqAsk() {
  const [routedTrack, setRoutedTrack] = useState<"telescope" | "microscope_nfl" | "microscope_cfb" | null>(null);
  const [question, setQuestion] = useState("");
  const [resolvedUnified, setResolvedUnified] = useState<UnifiedNlqEntity[]>([]);
  const [generatedSql, setGeneratedSql] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [userMessage, setUserMessage] = useState<string | null>(null);
  const [techDetail, setTechDetail] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const onAsk = useCallback(async () => {
    setUserMessage(null);
    setTechDetail(null);
    setGeneratedSql(null);
    setResult(null);
    setResolvedUnified([]);
    setRoutedTrack(null);

    const q = question.trim();
    if (!q) {
      setUserMessage("Enter a question first.");
      return;
    }

    setRunning(true);
    try {
      const state: TrackState = {
        setResolvedUnified,
        setGeneratedSql,
        setUserMessage,
        setTechDetail,
      };

      let sql: string;
      try {
        let dict;
        try {
          dict = await fetchHubDictionary();
        } catch (e) {
          state.setUserMessage("Could not load player dictionary (hub_dictionary.json). Run the data pipeline.");
          state.setTechDetail(e instanceof Error ? e.message : String(e));
          return;
        }

        const telescopeEntities = resolveNlqEntities(q, dict);
        const unifiedEntities = telescopeEntitiesToUnified(telescopeEntities, dict);
        state.setResolvedUnified(unifiedEntities);

        const resp = await requestUnifiedNlq(q, unifiedEntities);
        setRoutedTrack(resp.track);
        state.setGeneratedSql(resp.sql);
        sql = resp.sql;

        if (resp.track === "microscope_nfl" || resp.track === "microscope_cfb") {
          const fail = await mountNlqMicroscopeTrack(resp.track);
          if (fail) {
            state.setUserMessage(fail.message);
            if (fail.detail) {
              state.setTechDetail(fail.detail);
            }
            return;
          }
        } else {
          try {
            await ensureGoldTelescopeMounted(playerHubParquetUrl(), goldUnifiedParquetUrl());
          } catch (e) {
            state.setUserMessage("Telescope data (player_hub / gold_unified_performance) could not be loaded.");
            state.setTechDetail(e instanceof Error ? e.message : String(e));
            return;
          }
        }
      } catch (e) {
        state.setUserMessage(NLQ_USER_ERROR);
        state.setTechDetail(e instanceof Error ? e.message : String(e));
        return;
      }

      try {
        const rows = await runQuery(sql);
        setResult(rows);
      } catch (e) {
        setUserMessage(NLQ_USER_ERROR);
        setTechDetail(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setRunning(false);
    }
  }, [question]);

  return {
    routedTrack,
    question,
    setQuestion,
    resolvedUnified,
    generatedSql,
    result,
    userMessage,
    techDetail,
    running,
    onAsk,
  };
}
