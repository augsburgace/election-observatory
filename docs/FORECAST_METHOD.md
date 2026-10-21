# Analytical method and forecast publication policy

The application separates reported observations, conditional scenarios, and
validated forecasts. They are different evidence products. Registration, age,
race/ethnicity, voting method, and past county partisanship do not establish an
early voter's Senate choice.

## Current release status

The repository implements a real, deterministic Student-t simulation model,
rolling-origin historical evaluator, calibration diagnostics, and publication
gates. It does **not** contain a fabricated historical training corpus or a
passing validation artifact. Consequently, the default live application
withholds candidate-win and Senate-control probabilities. Missing historical
evidence is visible rather than replaced with illustrative numbers.

The tested simulator and backtesting tools are operational. A simulation run by
itself is an experiment; it does not establish that an election forecast is
calibrated. Synthetic fixtures in `backend/tests` cannot pass the publication
gate.

## Descriptive polling

The default series uses likely voters, vote-choice questions, full-ballot
configuration, and a fieldwork midpoint within the previous 21 days. Fieldwork
must have finished and the study must have been published or first observed by
the information cutoff. Date-only dashboard cutoffs include the entire
America/New_York calendar day. Timestamp cutoffs remain exact.

For every distinct candidate/question configuration:

1. Keep the newest eligible study per independent producer.
2. Deduplicate shared samples and co-published studies using stable study/sample
   identifiers. An older eligible study can remain when a newer one was not yet
   published at the cutoff.
3. Display an unweighted mean only with at least three independent producers.
4. Average only directly reported response categories common to the included
   studies. Do not turn censored values such as `<1%` into zero.
5. Preserve undecideds and other response categories. No automatic two-party
   normalization is applied.

The response lists included studies, exclusions, observed ranges,
leave-one-producer-out results, and a sponsorship sensitivity result. A
sensitivity result with fewer than three remaining producers withholds its
average as well. Three is a display threshold, not proof of survey reliability.

Registered-voter polls, winner-expectation questions, alternative ballots,
first-choice questions, and simulated final rounds remain separate. A reported
candidate-share margin of error is not reused as the margin-of-victory interval.

## Historical comparisons and chronology

The historical service accepts one metric, voting mode, time basis, and
demographic grain at a time. An `all` mode selects an explicit total rather than
adding possibly overlapping source categories. State totals never get added to
counties, districts, or precincts.

The default x-axis is signed days relative to Election Day, so negative 14 means
14 days before that cycle's Election Day. Days since a method opened and voting
opportunity indexes require explicit source/calendar metadata. They are not
estimated from a state's earliest observed record.

Historical pace is anchored to the latest actual current report/event date at
the selected reporting grain, rather than giving an older current report an
extra historical comparison day. The requested information cutoff is retained
separately. `comparison_anchor` exposes that date, its age, and days to Election
Day. Matched places with asynchronous or differently aligned reports carry an
explicit warning and retain both source dates.

Reported historical replay uses the document's established publication time.
When publication is unknown, first local observation is the earliest defensible
availability time. A later revised record uses its revision publication time,
or conservatively its first observation, rather than inheriting the original
record's publication time.

Reconstructed event-date history is explicitly labeled. Its cutoff selects
event dates within the pinned evidence revision, allowing later-obtained records
to reconstruct earlier participation. It does not establish what was publicly
known on those dates. Exact dataset revision filtering is applied upstream by
the storage/API layer before invoking these pure analytical functions.

Series advance only through observed dates. Geographic totals may carry a
place's last actual observation forward, retaining its date and reporting the
number of carried components. The first report from a newly covered geography
does not produce a purported daily vote increase. Negative changes remain
visible as corrections.

Matched comparisons use only shared, compatible reporting geographies. Unit,
metric-definition, grain, and known boundary-vintage conflicts prevent a match;
a documented verified crosswalk can establish compatibility. A geographic match
alone is not proof that voting rules or reporting definitions were unchanged.

## Scenario arithmetic

`run_scenario` takes explicit assumptions in percentages and ballot counts:

| Parameter | Meaning |
|---|---|
| `total_turnout` | Assumed final ballots; positive and at least the observed total |
| `observed_total` | Already reported ballots; supplied from selected evidence or explicitly as a scenario quantity |
| `observed_candidate_share` | Assumed candidate A share among reported ballots; required when observed total is positive |
| `observed_other_share` | Assumed share for other candidates among reported ballots |
| `remaining_candidate_share` | Candidate A share among remaining decided voters |
| `remaining_other_share` | Other candidates' share among remaining decided voters |
| `undecided_share` | Assumed undecided share among remaining voters |
| `undecided_allocation` | Assumed eventual candidate A share among those undecideds |

Candidate B is the remainder. For undecided fraction `u`, candidate A support
`a`, and allocation `q`, candidate A's effective remaining share is
`(1-u)*a + u*q`. Other support remains explicit. The output retains all votes;
other candidates are not silently excluded.

Optional `remaining_components` can describe one disjoint partition of remaining
votes by mode **or** geography. Their ballot counts must sum to the remaining
total and their candidate shares must be valid. Overlapping geographical and
voting-mode partitions must not be combined. Component scenarios suppress the
global automatic sensitivity grid because that grid would violate fixed
component totals.

The standard response includes the assumptions, final shares, margin in
percentage points, sensitivity intervals, and a two-dimensional turnout/support
grid. These are conditional calculations, not election probabilities.

`senate_scenarios` requires distinct contest identifiers, including special
elections, and explicit winner caucuses for assigned seats. Unassigned races and
unrepresented seats produce logical seat bounds. A 50–50 chamber requires a
vice-presidential tie-breaking assumption before interpreting control.

## Experimental empirical-Bayes model

Candidate margin is candidate A minus candidate B, in percentage points. Each
race requires a sourced fundamentals prior. Polling is optional in the
low-level simulator but required in historical cases comparing all three
baselines on identical case sets.

Initial cold-start parameters are:

- Polling error standard deviation: 4 points.
- Fundamentals error standard deviation: 8 points.
- Residual uncertainty floor: 2.5 points.
- Student-t degrees of freedom: 5.
- Shared national error fraction: 0.6 of the total error standard deviation.

These are explicit experimental assumptions, not claimed empirical findings.
Given at least five distinct earlier-cycle races, error means are shrunk toward
zero with five prior cases and scales are fitted from historical residuals.
Polling and fundamentals scale floors are 2 and 4 points respectively.
Repeated horizons for one race do not create additional independent scale-fit
records: the closest-to-election record is selected for each race/cycle.

For adjusted fundamentals prior `f`, polling estimate `p`, and error variances
`vf` and `vp`, the posterior center and variance are:

```text
posterior_variance = 1 / (1/vf + 1/vp)
center = posterior_variance * (f/vf + p/vp)
total_error_sd = sqrt(posterior_variance + residual_floor^2)
```

Student-t draws are rescaled to unit variance. Shared national and race-specific
components have squared coefficients summing to one. Margins are bounded to
[-100, 100]. The simulator reports margin distributions, 80%/95% intervals,
component weights, and seed. The default is 20,000 draws. APIs omit raw draw
arrays; `simulate_race` retains them for internal joint-model computation.

Early-voting predictors are excluded. Additional predictors require their own
timestamped historical corpus and demonstrated held-out benefit.

## Historical backtest import contract

The pure function `backtest_forecasts(cases, seed=2026, simulations=20000)` accepts
a JSON list. Each case supplies:

```json
{
  "race_id": "stable contest identifier, including seat/special distinction",
  "state": "two-letter state code",
  "cycle": 2022,
  "election_date": "2022-11-08",
  "cutoff": "2022-10-25",
  "result_margin": 0.0,
  "result_published_at": "2022-12-01",
  "data_origin": "historical",
  "inputs": {
    "election_system": "plurality",
    "polling_margin": 0.0,
    "polling_available_at": "2022-10-24",
    "fundamentals_margin": 0.0,
    "fundamentals_available_at": "2022-09-01",
    "sources": [
      {"source_id": "original evidence identifier", "available_at": "2022-09-01"}
    ]
  }
}
```

The zeros above illustrate field types, **not historical data**. A tied final
margin is excluded from the win-probability evaluator. Import actual certified
signed margins and original input evidence. Candidate A/B definitions must be
consistent for inputs and results.

The tool evaluates 30, 14, 7, and 1 days before Election Day. It rejects duplicate
race/cycle/horizon keys, late inputs, unsupported counting systems, invalid
results, and missing required chronology. Scale fitting uses only older cycles
whose result publication preceded the tested cutoff. No same-cycle results are
used to fit other races.

Outputs include case-level predictions, excluded records with reasons,
information splits, MAE, Brier score, log loss, interval coverage, calibration
bins, baseline scores, model parameters, and content hashes. Persist the complete
returned JSON; truncating or modifying it invalidates its integrity hash.

### Publication gate

Candidate probability release requires:

- At least 20 actual historical race/horizon cases across at least two cycles.
- Original source provenance for every case; synthetic records cannot validate.
- No silently excluded submitted records.
- For the requested horizon: at least three cases over at least two cycles.
- Combined-model MAE and Brier score no worse than both polling-only and
  fundamentals-only baselines on that same horizon's evaluation set.
- At least 65% observed coverage of 80% intervals and 85% coverage of 95%
  intervals at that horizon.
- Matching model version, passing artifact-integrity check, and no calibration
  cycle as recent as the live election cycle.
- Explicit live input chronology, election date, and supported election system.

Thresholds are a minimum operational gate. Small samples, repeated horizons,
selection bias, novel election conditions, and source gaps remain limitations.
Report actual results and retain the simpler model when complexity fails.

## Counting rules and chamber model

The implemented eventual-winner model supports plurality elections. Known
Alaska/Maine ranked-choice races and Georgia runoff resolution default to
unsupported, even if a caller omits `election_system`. Explicitly configured
first-choice or conditional contests must retain their actual scope; they must
not be presented as eventual-winner probabilities.

`forecast_senate` includes an actual shared-error simulation. It requires all 100
seats represented as contests or holdovers, distinct race identifiers, D/R
caucus assignments for every eventual winner, an explicit vice-presidential
caucus, supported race models, and **separate complete-universe correlation
validation**. Candidate-A conventions are sign-aligned to the national
Democratic error when simulating chamber outcomes.

Current race-level backtest artifacts deliberately set
`chamber_correlation_validated` to false. They cannot authorize Senate-control
probabilities. The local seat-scenario tool remains useful while complete
universe data, specialist counting-rule models, and correlation evidence are
unavailable.

## Reproduction and review

Forecast manifests retain inputs, seed, simulation count, model version,
validation hash, and manifest hash. Dataset revision and original snapshot
hashes are attached upstream in the research-package export. A stored seed
reproduces the computation for a fixed numerical runtime; library/platform
versions should be preserved for archival reproduction.

Meaningful automated tests cover duplicate polling samples, recency and release
cutoffs, unknown/censored values, historical revisions, coverage changes,
calendar alignment, impossible scenario totals, deterministic simulations,
rolling-cycle isolation, synthetic-data publication rejection, electoral-rule
gates, and incomplete chamber universes.
