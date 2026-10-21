# Public web reader

The public React build uses the same charts, maps and research screens as the local app. It reads validated aggregate publication files rather than running SQLite or source collection in visitors’ browsers.

## Build and test

```sh
pnpm --dir frontend typecheck
pnpm --dir frontend test
VITE_PUBLIC_DATA_MODE=true VITE_PUBLIC_BASE=/ pnpm --dir frontend exec vite build --outDir dist-public
```

The same reader and hash checks can smoke-test a local publication or the actual hosted artifacts:

```sh
node frontend/scripts/smoke-public-data.mjs .local/public-data .local/public-reader-proof.json --all-states
node frontend/scripts/smoke-public-data.mjs https://your-site.example/public-data/ .local/hosted-reader-proof.json --all-states
```

The remote check fetches the manifest once, permits only published aggregate artifact requests and uses the production reader’s gzip, pack, reference and SHA-256 logic. It rejects backend requests, altered evidence, unavailable pins and unsupported filters.

For a GitHub Pages project path, set `VITE_PUBLIC_BASE=/repository-name/`. The publisher/packer must copy a verified publication into `public-data/` beside this build. The ordinary `pnpm --dir frontend build` retains local API behavior and writes `frontend/dist`; keep the public build separate so the local application continues working.

## Evidence selection

`publicData.ts` resolves each API request against `/public-data/manifest.json`. It fills only the endpoint defaults declared by that manifest and sorts query parameters. Explicit revision, date, category, chronology, voting mode and other filters remain authoritative. An unpublished combination produces an explanation and available published investigations, never a response for a different selection.

A fresh URL containing only a state/page opens that state’s documented recommended investigation, pinned to the publication. Existing URLs and saved pins are preserved. Historical publications may not remain on the current free-host URL; an unavailable pin is explained rather than upgraded silently.

New map selections are `ui_selected_geographies` presentation state. Maps, rows and individual place trajectories highlight those places while statewide totals, calls and polling remain explicitly statewide. Existing evidence-filter URLs using `geography_ids` continue to mean actual filtered evidence; unpublished filters are not converted into presentation selections.

The manifest shows publication time separately from source reporting dates. A release older than six hours receives a delay notice; one older than 24 hours receives a stronger stale-data notice. The last successful publication remains readable during a source or publishing failure.

## Compact publication objects

Evidence inspectors use exact-ID buckets of at most 512 observation IDs. A bucket is keyed by `floor(id / 512)` and contains a direct exact-ID-to-evidence map (the earlier `{revision, items}` wrapper is also accepted); an ID absent from the published bucket remains unavailable. This reduces file counts without widening evidence access.

Responses can be plain JSON or content-addressed JSON structures. The reader verifies SHA-256 after decoding and resolves `$public_ref` objects and `$public_chunks` arrays into the original response shape. Raw gzip objects use the browser’s native `DecompressionStream`; HTTP `Content-Encoding: gzip` responses are already decoded and are not decompressed twice. Small objects can share physical gzip containers: `object_packs[logical_path]` indexes `packs[]`, and each decoded container maps exact original paths to original JSON text. The reader verifies both the container hash and the original fragment hash before hydrating. A mismatched/missing key is rejected. Eight decoded containers are retained, with at most four pack fetches in progress. Object promises use a bounded 384-entry cache; failed loads and corrupted responses are retryable.

## Private research and exports

Notes, exact-view configurations, bookmarks, scenarios and report configurations use this browser’s local storage. They are not uploaded. Clearing site storage removes them; the Notebook’s export action provides a user-owned JSON backup. Storage errors are surfaced instead of silently discarding notes.

Scenario arithmetic runs locally using the same constrained two-method calculation as the Python service. Reported participation constrains turnout; all support levels remain explicit assumptions. This is not a forecast.

The report composer selects and rearranges sections from an exact published report packet. Titles, captions and explicitly included notes are inserted as text. Changed evidence/result/context scopes must match the published packet. Exports support printable HTML, tables CSV, a research JSON packet and browser-print PDF. Private notes are omitted from JSON/HTML/CSV/PDF unless explicitly included. The full local edition retains server-generated PDF/ZIP and arbitrary source queries.

The reader never queues collection jobs, writes corrections or fetches private raw documents. Evidence links open original public sources. Sources also displays producer credits, license references, retrieval dates and transformation notes supplied by the publisher, including the attributed UF Election Lab historical bridge.
