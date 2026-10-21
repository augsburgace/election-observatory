import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import React from "react";
import { renderToString } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

test("an unavailable explanation service retains the exact pinned EV call and switches default off", async (t) => {
  const server = await createServer({
    root: fileURLToPath(new URL("..", import.meta.url)),
    configFile: false,
    esbuild: { jsx: "automatic" },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false },
    appType: "custom",
  });
  t.after(() => server.close());
  const { ForecastBriefing, localBriefing } = await server.ssrLoadModule(
    "/src/components/forecasts/ForecastBriefing.tsx",
  );
  const original = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-research-v1.1-oh.json", import.meta.url),
      "utf8",
    ),
  );
  const call = original.calls.find((row) => row.state === "OH"),
    frozen = JSON.stringify(call);
  const summary = localBriefing(call);
  assert.match(summary.headline, /Ohio: republicans ahead by 2\.8 points/);
  assert.match(summary.summary, /final historical results/);
  assert.match(summary.paragraphs[0].text, /do not reveal how people voted/);
  assert.equal(JSON.stringify(call), frozen);
  const previous = globalThis.location;
  t.after(() => {
    if (previous === undefined) delete globalThis.location;
    else globalThis.location = previous;
  });
  globalThis.location = new URL(
    "http://localhost/?state=OH&revision=176&as_of=2026-10-21",
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  t.after(() => client.clear());
  const render = () =>
    renderToString(
      React.createElement(
        QueryClientProvider,
        { client },
        React.createElement(ForecastBriefing, {
          call,
          cycle: 2026,
          revision: 176,
          asOf: "2026-10-21",
        }),
      ),
    ).replace(/<!-- -->/g, "");
  const evOnly = render();
  assert.match(evOnly, /Early-vote evidence only/);
  assert.equal((evOnly.match(/role="switch"/g) || []).length, 3);
  assert.doesNotMatch(evOnly, /checked=""/);
  assert.match(evOnly, /EV-only margin stays the same/);
  assert.match(evOnly, /r176/);
  globalThis.location.search +=
    "&ui_include_polls=true&ui_include_markets=true&ui_include_context=true";
  const withContext = render();
  assert.match(withContext, /EV \+ selected context/);
  assert.equal((withContext.match(/checked=""/g) || []).length, 3);
  assert.match(withContext, /The EV-only margin stays the same/);
  assert.equal(
    JSON.stringify(call),
    frozen,
    "requesting external context never mutates the stored EV prediction",
  );
});

test("reasoning and factor requests preserve cutoff and revision and send explicit false switches", async (t) => {
  const server = await createServer({
    root: fileURLToPath(new URL("..", import.meta.url)),
    configFile: false,
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false },
    appType: "custom",
  });
  t.after(() => server.close());
  const { earlyVoteReasoning, earlyVoteFeatureTests } =
    await server.ssrLoadModule("/src/earlyVoteApi.ts");
  const previous = globalThis.fetch,
    requests = [];
  t.after(() => {
    globalThis.fetch = previous;
  });
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return new Response(JSON.stringify({ revision: 176 }), { status: 200 });
  };
  const controller = new AbortController();
  await earlyVoteReasoning(
    {
      state: "OH",
      cycle: 2026,
      revision: 176,
      as_of: "2026-10-21",
      include_polls: false,
      include_markets: false,
      include_context: false,
    },
    controller.signal,
  );
  const request = new URL(requests[0].url, "http://localhost");
  assert.equal(request.pathname, "/api/v2/forecasts/reasoning");
  for (const key of ["include_polls", "include_markets", "include_context"])
    assert.equal(request.searchParams.get(key), "false");
  assert.equal(request.searchParams.get("revision"), "176");
  assert.equal(request.searchParams.get("as_of"), "2026-10-21");
  assert.equal(requests[0].options.signal, controller.signal);
  await earlyVoteFeatureTests({
    state: "OH",
    cycle: 2026,
    revision: 176,
    as_of: "2026-10-21",
  });
  assert.equal(
    new URL(requests[1].url, "http://localhost").pathname,
    "/api/v2/forecasts/feature-tests",
  );
});

test("the real added-factor audit shows sparse coverage and withholds unsupported accuracy scores", async (t) => {
  const server = await createServer({
    root: fileURLToPath(new URL("..", import.meta.url)),
    configFile: false,
    esbuild: { jsx: "automatic" },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false },
    appType: "custom",
  });
  t.after(() => server.close());
  const previousLocation = globalThis.location;
  t.after(() => {
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
  });
  globalThis.location = new URL("http://localhost/?state=OH&revision=266");
  const { FeatureTestResults, featureError } = await server.ssrLoadModule(
    "/src/components/forecasts/ForecastFeatureTests.tsx",
  );
  const response = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-feature-tests-r266.json", import.meta.url),
      "utf8",
    ),
  );
  assert.equal(
    response.feature_inventory.find(
      (feature) => feature.id === "stage_volume_log_change",
    ).available_cases,
    17,
  );
  assert.equal(
    response.feature_inventory.find(
      (feature) => feature.id === "precinct_distribution_shift_pp",
    ).available_cases,
    0,
  );
  assert.equal(
    featureError(response.headline_experiments[0].paired.augmented),
    null,
  );
  const markup = renderToString(
    React.createElement(FeatureTestResults, { data: response }),
  ).replace(/<!-- -->/g, "");
  assert.match(markup, /17 supported checkpoints/);
  assert.match(markup, /Change in which precincts turn out/);
  assert.match(markup, /Not testable yet/);
  assert.match(markup, /Not added to live calls/);
  assert.match(
    markup,
    /Repeated checkpoints do not increase the state-election count/,
  );
  assert.doesNotMatch(
    markup,
    /0\.00 points|Approved by validation|NaN|undefined|Infinity/,
  );
});

test("actual sourced Ohio explanations challenge the EV call with outside evidence while preserving its point", async (t) => {
  const server = await createServer({
    root: fileURLToPath(new URL("..", import.meta.url)),
    configFile: false,
    esbuild: { jsx: "automatic" },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false },
    appType: "custom",
  });
  t.after(() => server.close());
  const { ForecastBriefing } = await server.ssrLoadModule(
    "/src/components/forecasts/ForecastBriefing.tsx",
  );
  const previousLocation = globalThis.location;
  t.after(() => {
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
  });
  const readingLabels = await server.ssrLoadModule("/src/forecastReadingLabels.ts");
  assert.equal(readingLabels.fieldworkLabel("2026-10-15", "2026-10-18"), "Oct 15, 2026 – Oct 18, 2026");
  assert.equal(readingLabels.fieldworkLabel("2026-02-31"), "date unavailable");
  assert.equal(readingLabels.populationLabel("LV"), "Likely voters");
  assert.equal(readingLabels.populationLabel("RV"), "Registered voters");
  assert.equal(readingLabels.populationLabel("A"), "Adults");
  assert.match(readingLabels.easternTimeLabel("2026-10-21T16:32:12.993221+00:00"), /Oct 21, 2026.*12:32 PM EDT/);
  assert.match(readingLabels.easternTimeLabel("2026-12-21T16:32:12Z"), /11:32 AM EST/);
  assert.equal(readingLabels.easternTimeLabel("2026-10-21T16:32:12"), "time unavailable");
  const responses = await Promise.all(
    ["evonly", "all"].map(async (mode) =>
      JSON.parse(
        await readFile(
          new URL(`./fixtures/reasoning-oh-${mode}-r375.json`, import.meta.url),
          "utf8",
        ),
      ),
    ),
  );
  assert.deepEqual(responses[0].ev_call.call, responses[1].ev_call.call);
  assert.equal(
    responses[0].manifest.ev_call_sha256,
    responses[1].manifest.ev_call_sha256,
  );
  assert.equal(responses[1].signals.polls.studies.length, 5);
  assert.equal(responses[1].signals.markets.markets.length, 2);
  for (const response of responses) {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    t.after(() => client.clear());
    const switches = response.switches;
    globalThis.location = new URL(
      `http://localhost/?state=OH&revision=375&ui_include_polls=${switches.polls}&ui_include_markets=${switches.markets}&ui_include_context=${switches.context}`,
    );
    client.setQueryData(
      [
        "forecast-reasoning",
        "OH",
        response.ev_call.race_id,
        2026,
        375,
        response.as_of,
        switches.polls,
        switches.markets,
        switches.context,
      ],
      response,
    );
    const markup = renderToString(
      React.createElement(
        QueryClientProvider,
        { client },
        React.createElement(ForecastBriefing, {
          call: response.ev_call,
          cycle: 2026,
          revision: 375,
          asOf: response.as_of,
        }),
      ),
    ).replace(/<!-- -->/g, "");
    assert.match(markup, /Republicans ahead by 2\.8 points/);
    assert.match(markup, /What has actually happened/);
    assert.match(markup, /Which places explain the change/);
    assert.match(markup, /Turnout can change the story/);
    assert.match(markup, /EV-only margin stays the same/);
    assert.doesNotMatch(markup, /NaN|undefined|Infinity|\[object Object\]/);
    if (response.mode === "ev_only") {
      assert.match(markup, /Early-vote evidence only/);
      assert.doesNotMatch(
        markup,
        /Marist Poll|Polymarket|Toss Up|contract price|checked=""/,
      );
    } else {
      assert.equal((markup.match(/checked=""/g) || []).length, 3);
      assert.match(markup, /Marist Poll/);
      assert.match(markup, /Sherrod Brown/);
      assert.match(markup, /Jon Husted/);
      assert.match(markup, /Oct 15, 2026 – Oct 18, 2026/);
      assert.match(markup, /Likely voters/);
      assert.match(markup, /title="2026-10-15 – 2026-10-18"/);
      assert.match(markup, /12:32 PM EDT/);
      assert.match(markup, /Undecided/);
      assert.match(markup, /Sample not disclosed/);
      assert.match(markup, /Secondary summary/);
      assert.match(markup, /Polymarket/);
      assert.match(markup, /65\.5%/);
      assert.match(markup, /contract price/);
      assert.match(markup, /Provider updated/);
      assert.match(markup, /Contract settlement rules/);
      assert.match(markup, /RCP published race rating: Toss Up/);
      assert.match(markup, /Do the outside signals agree/);
      assert.match(markup, /challenges the EV call/);
      assert.match(markup, /https:\/\/maristpoll\.marist\.edu/);
      assert.match(
        markup,
        /https:\/\/polymarket\.com\/event\/ohio-senate-election-winner/,
      );
      assert.match(markup, /Use early votes only/);
    }
  }
});
