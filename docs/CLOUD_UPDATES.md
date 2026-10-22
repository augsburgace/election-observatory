# Free scheduled cloud updates

The public distribution is [augsburgace/election-observatory](https://github.com/augsburgace/election-observatory). Its application address is [the election research atlas](https://augsburgace.github.io/election-observatory/). The separate private development repository and its history are preserved. A reviewed source snapshot is exported with `scripts/prepare_public_source.py`; old local verification documents containing saved-view metadata are replaced in the public copy.

## What runs in the cloud

The `Public cloud updates` GitHub Actions workflow uses a standard `ubuntu-24.04` runner in the public repository. Its schedule is `17 */2 * * *` UTC: approximately every two hours, at minute 17. GitHub can delay or miss scheduled jobs; this is a best-effort research publisher, without a continuous-compute or availability guarantee. Collection does not require the owner's Mac to be running.

The workflow has no pull-request or untrusted-fork execution path. It runs only on the approved public repository's `main` branch. Its actions are pinned to reviewed commit SHAs. Credentials use GitHub's short-lived workflow token and Pages deployment identity. No personal GitHub token, Cloudflare login, external AI key, paid runner, paid database, LFS purchase or cloud subscription is required.

The first complete cloud publication passed at revision 592 on October 21, 2026. It took approximately two hours, including collection, the full analytical rebuild, checkpoint preparation and hosted verification. Source checks occur at the beginning of a run; a newly published website is not evidence that every authority reported new figures at that publication time. Long runs serialize, and missed or delayed schedules can extend the interval. A subsequent exact-byte compression cache avoids recompressing identical geometry; its output equivalence is tested, but a complete future cloud runtime is not yet measured. Read the [release record](CLOUD_WEB_RELEASE.md) for the observed result.

### Efficient unchanged checks

After checking due sources, the worker compares the validated revision, New York research date, source availability/caveats, application address, and a fingerprint of the application, parsers, source configuration and locked dependencies with the actual hosted manifest. If all agree, it skips the full fifty-state analytical rebuild, checkpoint ZIP/VACUUM, artifact upload and deployment. A new day refreshes date-sensitive analyses even without new ballots. Code/configuration changes and changed source availability also force a build. The first run after installing this gate performs a full build to establish its baseline. Manual **force** always rebuilds; disabling **collect** also explicitly rebuilds the restored evidence.

Successful unchanged runs write a small public [source-check receipt](https://github.com/augsburgace/election-observatory/blob/main/source-check-state.json). It records check time, source identifiers, document hashes and status, without original records or raw errors. Only successful check clocks matching the exact checkpoint and document hash are restored on the next worker. This retains each source's configured cadence without exporting the large database on an unchanged check. Receipts cannot alter evidence, revisions, warnings or source status; failed checks are not deferred by a receipt.

The receipt and the existing `publication-state.json` deliberately describe different events: checking an unchanged source does not invent a new observation or publication. Each completed check creates genuine repository activity even when voting is unchanged, helping avoid GitHub's inactivity-based schedule suspension. Failed runs remain visible in Actions; extended outages, policy changes or an account suspension still require intervention.

1. Restore a checksum-verified public collector checkpoint from a completed release.
2. Retain the exact prior website by its complete publication-manifest hash.
3. Check due public sources and calculate the analysis, preserving source-specific errors and the last valid observations.
4. Freeze the local database revision, build all 50 states, verify raw and packed research readers, and compile the real application.
5. Export a sanitized successor checkpoint. Verify it has no private research or job rows.
6. Preserve the validated checkpoint and matching website together in a unique release **before** changing the live site.
7. Deploy through GitHub Pages and verify the exact hosted manifest and the 75-check all-state reader.
8. Record actual successful publication status in `publication-state.json` and rotate only generated collector checkpoints, retaining three verified states plus bootstrap.

A validated checkpoint can be newer than the currently hosted website if deployment failed. It is not labeled as a successful website release until hosted verification passes. Rollback locates the exact previous manifest, including when multiple application builds share the same evidence revision.

## Data and privacy

Public release assets include normalized aggregate evidence, historical results, public boundary geometry, source metadata, the two fixed original Census county-change reference pages, and the reviewed factual polling-table captures required to preserve their lineage. These are collector checkpoints, **not private full-store backups**. The Census documents use an exact source/URL/type/size/hash whitelist. Missing or corrupted originals withhold county differences while preserving the two original result sets.

Private notebooks, saved personal investigations, job history, private correction reasons, credentials and original voter-file archives are excluded. The exporter scrubs deleted SQLite cells and vacuums the copy, sanitizes all small geometry metadata JSON, and checks member hashes. Published report and map objects retain their existing privacy filters. Raw downloads made on the ephemeral runner are not part of its next checkpoint or website.

Individual source authorities can block cloud-hosted requests. Failures remain visible in source health, and existing validated observations remain available. Browser-only RCP captures retain their actual capture dates; the cloud workflow does not pretend to refresh them unattended. Historical EV gaps, absent demographic categories, unsupported joint filters and experimental forecast limits remain explicit.

## Free-resource limits

- Standard public-repository Actions runners are free; larger paid runners are not selected.
- Checkpoints use GitHub Releases with each asset below 2 GiB, rather than Git LFS or retained Actions caches.
- Published websites are limited to 950 MB, below Pages' 1 GB site limit. A stricter estimated 400 MB temporary-artifact gate bounds this workflow's use of Actions storage. Completed temporary deployment artifacts are deleted immediately, including rollback artifacts.
- Checkpoints retain three verified generated states plus protected bootstrap. Other releases, private backups and private history are never rotated by this workflow.
- The worker needs at least 25 GB free before restoring evidence because SQLite backup and vacuum can temporarily require several database-sized files. Only unused SDK directories on the disposable hosted runner are reclaimed. Insufficient disk stops the run before publication.
- Pages has a soft bandwidth limit. Hosting limits, source availability and GitHub's schedule policies still apply. No automatic paid upgrade is configured.

Successful publication and source-check commits provide an operations trail. GitHub's scheduling remains best effort; the retained validated website continues to work during a delayed or failed check.

## Operate and inspect

From the public repository, use **Actions → Public cloud updates → Run workflow**. Leave **collect** enabled for ordinary refreshes. **bootstrap** is only for the initial verified setup when the Pages site has not yet been published. An unexpected missing live site on a later run fails closed.

```sh
gh workflow run public-cloud.yml --repo augsburgace/election-observatory -f collect=true
gh run list --repo augsburgace/election-observatory --workflow public-cloud.yml --limit 5
gh api repos/augsburgace/election-observatory/contents/publication-state.json --jq .content
gh api repos/augsburgace/election-observatory/contents/source-check-state.json --jq .content
```

The last command returns base64 content from the public status file. The repository's normal file viewer shows decoded JSON. The website's publication banner and each source's reporting date describe different clocks; read both before interpreting change.

Build and pre-deployment failures leave the previous website alone. A failed deployment or hosted-reader check triggers an exact prior-site deployment and its own hosted-reader verification. The workflow remains failed after a successful rollback. If rollback verification fails, inspect the live manifest and Actions log; do not claim recovery until verified.

On the first deployment there is no prior GitHub Pages website to restore. Bootstrap evidence is never presented as that missing prior website. Actual rollback sites and new publications must contain existing application assets under `/election-observatory/`, so a correct data manifest cannot conceal an incompatible browser build.

The local application, personal database and local source archives remain separate. The Mac's launchd job runs collection only; it does not publish over the cloud edition or the archived site. To reinstall that local-only schedule, run `.venv/bin/python scripts/install_schedule.py --defer-first-run` from the local checkout.

The original [Cloudflare address](https://battleground-senate-observatory.pages.dev) preserves the initial revision and provides a prominent link to the cloud-updated edition. It remains a functional archive rather than redirecting automatically, because browser-local notebooks belong to that original origin. Download a notebook there to keep a portable backup. New notes at the GitHub address remain local to that browser and origin too.

Official references: [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits), [release asset limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), [scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
