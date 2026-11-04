/**
 * Prints how the rules parser does on the eval questions: how many it answers correctly, hands to the
 * model, or gets wrong. Run: npm run eval:rules
 */
import { runRulesEval } from "../src/features/nlq/ruleEval";
import { FIXTURE_SEASONS } from "../src/test/seasons";

const rows = runRulesEval(FIXTURE_SEASONS);
const out = (line: string) => process.stdout.write(`${line}\n`);

for (const set of ["cases", "heldout"] as const) {
  const mine = rows.filter((r) => r.set === set);
  // Questions marked rules:"defer" are answerable, but the rules should hand them over.
  const answerable = mine.filter((r) => !r.case.unsupported && r.case.rules !== "defer");
  const count = (v: string, of = mine) => of.filter((r) => r.verdict === v).length;

  out(`\n${set}: ${mine.length} questions (${answerable.length} for the rules to answer, ${mine.length - answerable.length} to refuse or hand over)`);
  out(`  answered correctly by rules: ${count("correct", answerable)}/${answerable.length}`);
  out(`  handed to the model:         ${count("deferred")}`);
  out(`  wrong:                       ${count("wrong")}`);
  for (const r of mine.filter((x) => x.verdict !== "correct")) {
    const detail = r.result.status === "resolved" ? JSON.stringify(r.result.intent) : r.result.reason;
    out(`    [${r.verdict}] ${r.case.q}\n        ${r.result.status}: ${detail}`);
  }
}
