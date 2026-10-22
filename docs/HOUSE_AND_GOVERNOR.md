# House and governor research

The Forecasts page has an office selector for Senate, House and Governor. Existing Senate URLs and model contracts remain unchanged. New views retain `ui_forecast_office`, `ui_forecast_race`, the evidence revision and cutoff in the URL and saved layout.

## Coverage

- Registry: 435 regular House seats across 50 states; 36 scheduled state governor races in 2026. Territories/delegates and separately scheduled special House elections are explicitly outside this registry.
- House history: the existing district-return archive. At r593, 432 current district numbers had some historical record. The additional attributed House bridge raises this to all 435 at r660 and fills 2020 gaps. An added or renumbered district can have no matching historical number. District numbers do **not** establish continuity across redistricting.
- Governor history: Cha, Kuriwaki and Snyder, *Candidates in American General Elections*, Harvard Dataverse, DOI [10.7910/DVN/DGDRDT](https://doi.org/10.7910/DVN/DGDRDT), CC0. The pinned producer file contains 2006–2024 records. The first governor import publishes 1,012 candidate records across all 50 states in a new revision; dedicated official returns retain precedence. All 36 scheduled 2026 governor races have archived history at r593.
- The companion House collection uses the same producer file, compiled from House Clerk election statistics. The loader publishes 11,718 candidate records (including separately labeled special contests); incomplete numeric cells remain missing. Within an election, district labels such as 1/01/001 select one complete producer rather than duplicating or merging its candidate rows. This alias resolution does not imply cross-year boundary continuity.
- The academic producer excludes candidates with fewer than ten votes, blank/miscellaneous party records and invalid votes. Candidate-vote totals are not turnout. Deciding runoffs remain distinct stages with unknown dates unless separately documented. Current candidate rosters are not inferred from history. Revision 659 preserves the original archive while replacing three special-election GEN groupings with distinct special stages and unknown dates; no November date is invented for those specials.

The universe uses Census apportionment, the FEC election calendar and the NGA calendar. Office-specific rules cite Alaska, Maine, Georgia and Louisiana authorities. The Louisiana 2026 House registry identifies the November 3 open primary and potential December 12 final runoff. Maine's governor general election is distinct from federal ranked-choice contests.

## Interpretation and forecasts

New office desks provide actual blue/red historical margins, complete retained candidate shares, election-type labels, current state participation, the existing same-stage EV workbench, nationwide coverage maps, searchable race boards, saved views and exact-race exports.

Governor historical references use earlier governor outcomes of the same election type. At r593 the separate retrospective governor baseline has 93 tests at 2018/2020/2022/2024 origins and an approximately 13.1-point MAE. That relatively large error illustrates why a historical lean is not sufficient for a current call. These tests do not validate an EV adjustment or probabilities.

House projections are withheld until current boundaries, district-level EV and compatible historical observations are verified. No county/state total is prorated into districts, and no Senate coefficients, polling records, market contracts or backtest scores become House/governor evidence. Outside-evidence controls explain the missing office-specific connectors instead of substituting Senate data. No winner probabilities are published for either new office.

Final returns from the cutoff year or later are excluded. Historical returns are retrospective evidence, not a claim of contemporary publication availability. Pinned older revisions never acquire the newly installed governor archive.

## Reports and operations

“Build this race report” opens the report composer with the exact office, race ID, state, revision and cutoff. The House/governor template combines race history, candidate tables, statewide participation, source hashes and limitations. Local exports include PDF/HTML/CSV/JSON/ZIP. Public browser reports support HTML/CSV/JSON and print-to-PDF using the same published office evidence, with escaped text and source hashes.

`GET /api/v2/forecasts/offices?office=US%20HOUSE|GOVERNOR&cycle=2026&revision=...&as_of=...` returns a compact nationwide office packet. The free publisher stores two shared packets rather than hundreds of repeated state workspaces. Public reader checks verify the universe, revision, chronology and withheld House estimates.

Install the additional reference source with:

```sh
.venv/bin/observatory atlas --dataset snyder_governor_2006_2024
```

The companion House source is `snyder_house_2006_2024`. Both are part of `atlas --core`. The normal cloud collection job installs it once, then skips already validated content. Original snapshots remain content-addressed outside Git. Source failures preserve validated content and the previous public release.

Verification: `pytest`, Ruff, frontend tests, TypeScript, Vite; browser checks cover office/district switching, the exact-race report, both themes and narrow screens. Test fixtures are explicitly isolated; the frontend regression fixture contains only archived public aggregate Ohio candidate returns.

For a presentation-only correction, the cloud workflow accepts `shell_only=true`. This mode refuses backend, source, or analytical changes since the verified release. It retains the exact aggregate objects and sanitized seed, rebuilds the browser application, verifies the complete bundle and hosted reader, and preserves normal checkpoint/rollback protection. It does not claim to have checked new sources. Scheduled collection continues through the full publication path.
