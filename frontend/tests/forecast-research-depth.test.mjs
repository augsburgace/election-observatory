import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  forecastMapRows,
  nationalCallRows,
  selectedCaseMetrics,
} from "../src/forecastResearchMath.ts";
const fixture = JSON.parse(
  await readFile(
    new URL("./fixtures/ev-research-v1.1-oh.json", import.meta.url),
    "utf8",
  ),
);
const ohio = fixture.calls.find((row) => row.state === "OH");
test("geographic forecast maps preserve the exact model IDs, measurements and separate contextual quantities", () => {
  const measured = forecastMapRows(ohio, "volume"),
    historical = forecastMapRows(ohio, "margin"),
    contribution = forecastMapRows(ohio, "contribution");
  assert.equal(measured.length, ohio.evidence.geographic_tilt.rows.length);
  for (let index = 0; index < measured.length; index++) {
    const source = ohio.evidence.geographic_tilt.rows[index];
    assert.equal(measured[index].id, source.id);
    assert.equal(measured[index].value, source.early_votes);
    assert.equal(
      measured[index].change,
      null,
      "measured EV never becomes historical candidate margin",
    );
    assert.equal(historical[index].change, source.reference_margin_pp);
    assert.equal(contribution[index].change, source.contribution_pp);
    assert.equal(
      contribution[index].denominator,
      null,
      "no inferred turnout denominator",
    );
    assert.equal(contribution[index].share, source.early_share_pct / 100);
  }
});
test("two Senate races in one state are not silently merged into a state margin", () => {
  const other = {
    ...ohio,
    race_id: "separate-special",
    call: { ...ohio.call, margin_pp: -20 },
  };
  assert.equal(nationalCallRows([ohio, other])[0].value, null);
  assert.equal(nationalCallRows([ohio, other], other.race_id)[0].value, -20);
  assert.equal(nationalCallRows([ohio])[0].value, ohio.call.margin_pp);
});
test("repeated cutoffs receive one contest weight rather than inflating independent evidence", () => {
  const repeated = Array.from({ length: 10 }, (_, index) => ({
    state: "NC",
    year: 2020,
    contest_id: "a",
    cutoff: String(index),
    error_pp: 10,
    baseline_error_pp: 12,
  }));
  const single = {
    state: "NC",
    year: 2022,
    contest_id: "b",
    error_pp: 0,
    baseline_error_pp: 4,
  };
  const summary = selectedCaseMetrics([...repeated, single]);
  assert.equal(summary.cases, 11);
  assert.equal(summary.contests, 2);
  assert.equal(summary.mae, 5);
  assert.ok(Math.abs(summary.referenceMae - 8) < 1e-12);
  assert.equal(summary.bias, 5);
  assert.equal(selectedCaseMetrics([]), null);
});
