import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import React from "react";
import { renderToString } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

test("the real Forecasts component renders actual v1.1 response shapes with the compact source-omitting bootstrap", async (t) => {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const server = await createServer({
    root,
    configFile: false,
    esbuild: { jsx: "automatic" },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null },
    appType: "custom",
  });
  t.after(() => server.close());
  const { default: Forecasts } = await server.ssrLoadModule(
    "/src/pages/Forecasts.tsx",
  );
  const bootstrap = JSON.parse(
    await readFile(
      new URL("./fixtures/bootstrap-compact.json", import.meta.url),
      "utf8",
    ),
  );
  assert.equal(
    Object.hasOwn(bootstrap, "sources"),
    false,
    "production bootstrap deliberately omits the full source inventory",
  );
  const response = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-research-v1.1-oh.json", import.meta.url),
      "utf8",
    ),
  );
  const previousLocation = globalThis.location;
  t.after(() => {
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
  });
  for (const state of ["OH", "AK", "CA"]) {
    const query = {
      state,
      cycle: 2026,
      baseline: 2022,
      revision: response.revision,
      as_of: response.as_of,
      time_basis: "reported",
      metric: "ballots_cast",
      mode: "all",
      geography_ids: [],
      alignment: "days_to_election",
      date_window: [],
    };
    const selected =
      response.calls.find((call) => call.state === state) || null;
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    client.setQueryData(
      ["early-vote-calls", state, 2026, response.revision, response.as_of],
      { ...response, selected },
    );
    globalThis.location = new URL(
      `http://localhost/?state=${state}&page=forecasts`,
    );
    const noop = () => {};
    const markup = renderToString(
      React.createElement(
        QueryClientProvider,
        { client },
        React.createElement(Forecasts, {
          bootstrap,
          workspace: {
            revision: response.revision,
            observations: [],
            warnings: [],
            query,
          },
          query,
          setQuery: noop,
          setPage: noop,
          inspect: noop,
          notify: noop,
          refresh: noop,
          refreshing: false,
        }),
      ),
    );
    assert.match(markup, /Early voting, interpreted/);
    if (state === "OH") {
      assert.match(markup, /Unvalidated sensitivity range/);
      assert.match(markup, /Build this Senate report/);
      assert.match(markup, /Matched share of statewide quantity/);
    } else if (state === "AK")
      assert.match(markup, /No D\/R point or sensitivity range is published/);
    else assert.match(markup, /has no selected Senate contest/);
    assert.doesNotMatch(
      markup,
      /No validated live model runs/,
      "the closed probability gate is lazy and does not fetch or render its detailed model",
    );
    client.clear();
  }
});

test("expanded forecasts render genuine held-out audit cases, low confidence, source-native maps and evaluated sensitivity inputs", async (t) => {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const server = await createServer({
    root,
    configFile: false,
    esbuild: { jsx: "automatic" },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null },
    appType: "custom",
  });
  t.after(() => server.close());
  const { default: Forecasts } = await server.ssrLoadModule(
    "/src/pages/Forecasts.tsx",
  );
  const bootstrap = JSON.parse(
    await readFile(
      new URL("./fixtures/bootstrap-compact.json", import.meta.url),
      "utf8",
    ),
  );
  const response = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-research-expanded-nc.json", import.meta.url),
      "utf8",
    ),
  );
  assert.equal(
    response.backtesting.cases.length,
    14,
    "fixture is the actual r242 held-out audit, not illustrative predictions",
  );
  assert.deepEqual(response.backtesting.independent_cycles, [2020, 2022]);
  const query = {
    state: "NC",
    cycle: 2026,
    baseline: 2022,
    revision: response.revision,
    as_of: response.as_of,
    time_basis: "reported",
    metric: "ballots_cast",
    mode: "all",
    geography_ids: [],
    alignment: "days_to_election",
    date_window: [],
  };
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(
    ["early-vote-calls", "NC", 2026, response.revision, response.as_of],
    response,
  );
  const previousLocation = globalThis.location;
  t.after(() => {
    client.clear();
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
  });
  globalThis.location = new URL("http://localhost/?state=NC&page=forecasts");
  const noop = () => {};
  const markup = renderToString(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(Forecasts, {
        bootstrap,
        workspace: {
          revision: response.revision,
          observations: [],
          warnings: [],
          query,
        },
        query,
        setQuery: noop,
        setPage: noop,
        inspect: noop,
        notify: noop,
        refresh: noop,
        refreshing: false,
      }),
    ),
  );
  const visible = markup.replace(/<!-- -->/g, "");
  assert.match(markup, /Low forecasting confidence/);
  assert.match(markup, /No win probabilities published/);
  assert.match(markup, /No validated win probability/);
  assert.match(visible, /8 cutoff tests · 2 independent contests/);
  assert.match(markup, /contemporary-input tests/);
  assert.match(markup, /Retrospective report archive/);
  assert.match(markup, /Trained EV model/);
  assert.match(markup, /Not calibrated/);
  assert.match(markup, /EV conversion coefficient numeric value/);
  assert.match(markup, /Negative values test reversal/);
  assert.match(markup, /Measured EV volume/);
  assert.match(markup, /Historical party context/);
  assert.match(markup, /Geographic contribution/);
  assert.match(visible, /Inspect all 100 geographic model inputs/);
  assert.doesNotMatch(markup, /No validated live model runs/);
});

test("real stage workbench renders supported NC comparisons and honest OH gaps with conditional turnout kept separate", async (t) => {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const server = await createServer({
    root,
    configFile: false,
    esbuild: { jsx: "automatic" },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null },
    appType: "custom",
  });
  t.after(() => server.close());
  const { ForecastHistory, stageChartRows } = await server.ssrLoadModule(
    "/src/components/forecasts/ForecastHistory.tsx",
  );
  const bootstrap = JSON.parse(
    await readFile(
      new URL("./fixtures/bootstrap-compact.json", import.meta.url),
      "utf8",
    ),
  );
  const oldCalls = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-research-v1.1-oh.json", import.meta.url),
      "utf8",
    ),
  );
  const ncCalls = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-research-expanded-nc.json", import.meta.url),
      "utf8",
    ),
  );
  const previousLocation = globalThis.location;
  t.after(() => {
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
  });
  for (const state of ["NC", "OH"]) {
    const response = JSON.parse(
      await readFile(
        new URL(
          `./fixtures/ev-stage-r253-${state.toLowerCase()}.json`,
          import.meta.url,
        ),
        "utf8",
      ),
    );
    const call =
      state === "NC"
        ? ncCalls.selected
        : oldCalls.calls.find((row) => row.state === state);
    const query = {
      state,
      cycle: 2026,
      baseline: 2022,
      revision: response.revision,
      as_of: response.query.as_of,
      time_basis: "reported",
      metric: "ballots_cast",
      mode: "all",
      geography_ids: [],
      alignment: "days_to_election",
      date_window: [],
    };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    client.setQueryData(
      [
        "ev-stage-history",
        state,
        2026,
        response.revision,
        response.query.as_of,
        "ballots_cast",
        "all",
        "days_to_election",
        "retrospective",
        "2016,2018,2020,2022,2024",
      ],
      response,
    );
    globalThis.location = new URL(
      `http://localhost/?state=${state}&page=forecasts`,
    );
    const noop = () => {};
    const markup = renderToString(
      React.createElement(
        QueryClientProvider,
        { client },
        React.createElement(ForecastHistory, {
          ctx: {
            bootstrap,
            workspace: { revision: response.revision, query },
            query,
            setQuery: noop,
            setPage: noop,
            inspect: noop,
            notify: noop,
            refresh: noop,
            refreshing: false,
          },
          call,
          revision: response.revision,
          asOf: response.query.as_of,
        }),
      ),
    ).replace(/<!-- -->/g, "");
    assert.match(markup, /Same stage, different elections/);
    assert.match(markup, /Historical EV evidence vintage/);
    assert.match(markup, /Turnout is central/);
    assert.match(markup, /Current quantity \/ registration/);
    assert.match(
      markup,
      /Historical final-participation sources and definitions/,
    );
    assert.match(markup, /Lower turnout/);
    assert.match(markup, /Prior-cycle turnout/);
    assert.match(markup, /Higher turnout/);
    assert.match(markup, /not a fitted turnout forecast/);
    assert.match(markup, /Voting methods and administrative measures/);
    assert.match(markup, /not stacked or added into a manufactured total/);
    assert.doesNotMatch(markup, /NaN|undefined|Infinity/);
    if (state === "NC") {
      assert.equal(response.coverage.same_stage_cycles, 4);
      assert.match(markup, /4 \/ 5/);
      assert.match(markup, /924,160/);
      assert.match(markup, /Exact stage · compatible/);
      const chart = stageChartRows(response, "days_to_election");
      const sourcePoints = [
        { cycle: 2026, trajectory: response.current.trajectory },
        ...response.cycles,
      ];
      for (const row of chart) {
        for (const source of sourcePoints) {
          if (row[`cycle_${source.cycle}`] != null)
            assert.ok(
              source.trajectory.some(
                (point) =>
                  point.days_to_election === row.coordinate &&
                  point.value === row[`cycle_${source.cycle}`],
              ),
              "every plotted value is an actual supplied observation, not an interpolated fact",
            );
        }
      }
    } else {
      assert.equal(response.coverage.same_stage_cycles, 0);
      assert.match(markup, /0 \/ 5/);
      assert.match(markup, /Pace ratio withheld/);
      assert.match(markup, /676,836/);
      assert.match(
        markup,
        /No eligible observation of this exact metric and method/,
      );
    }
    client.clear();
  }
});

test("shared national map distinguishes conditional research margins from historical context and labels signed margins accessibly", async (t) => {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const server = await createServer({
    root,
    configFile: false,
    esbuild: { jsx: "automatic" },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null },
    appType: "custom",
  });
  t.after(() => server.close());
  const { NationalMap } = await server.ssrLoadModule(
    "/src/components/Maps.tsx",
  );
  const { nationalCallRows } = await server.ssrLoadModule(
    "/src/forecastResearchMath.ts",
  );
  const response = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-research-v1.1-oh.json", import.meta.url),
      "utf8",
    ),
  );
  const boundaries = JSON.parse(
    await readFile(
      new URL("../public/geography/states.geojson", import.meta.url),
      "utf8",
    ),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  t.after(() => client.clear());
  client.setQueryData(["boundaries", "US"], boundaries);
  const props = {
    rows: nationalCallRows(response.calls),
    selected: "OH",
    onSelect: () => {},
    layer: "margin",
  };
  const render = (extra) =>
    renderToString(
      React.createElement(
        QueryClientProvider,
        { client },
        React.createElement(NationalMap, { ...props, ...extra }),
      ),
    ).replace(/<!-- -->/g, "");
  const conditional = render({
    marginContext: "Conditional research margin · R−D percentage points",
    missingLabel: "No published conditional margin; open available research",
  });
  assert.match(
    conditional,
    /Conditional research margin · R−D percentage points/,
  );
  assert.doesNotMatch(conditional, /certified historical context/);
  assert.match(conditional, /aria-label="Ohio, R \+2\.8 pp"/);
  assert.match(conditional, /No published conditional margin/);
  const historical = render({});
  assert.match(
    historical,
    /Percentage points · certified historical context/,
    "the original historical legend remains the default for existing callers",
  );
  const tiles = render({
    tile: true,
    marginContext: "Conditional research margin · R−D percentage points",
  });
  assert.match(tiles, /aria-label="Ohio, R \+2\.8 pp"/);
  assert.match(tiles, />R \+2\.8 pp</);
});

test("opening-day chart defaults to nonnegative actual observations while preserving optional pre-opening reports", async (t) => {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const server = await createServer({
    root,
    configFile: false,
    esbuild: { jsx: "automatic" },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null },
    appType: "custom",
  });
  t.after(() => server.close());
  const { ForecastHistory, stageChartRows } = await server.ssrLoadModule(
    "/src/components/forecasts/ForecastHistory.tsx",
  );
  const response = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-stage-r253-nc-opening.json", import.meta.url),
      "utf8",
    ),
  );
  const original = JSON.stringify(response);
  const visible = stageChartRows(response, "days_since_opening");
  const raw = stageChartRows(response, "days_since_opening", true);
  assert.equal(response.current.days_since_opening, 6);
  assert.equal(Math.min(...raw.map((row) => row.coordinate)), -40);
  assert.equal(Math.min(...visible.map((row) => row.coordinate)), 0);
  assert.ok(visible.every((row) => row.coordinate >= 0));
  assert.ok(raw.length > visible.length);
  assert.equal(
    JSON.stringify(response),
    original,
    "the display default does not alter original records or export data",
  );
  const call = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-research-expanded-nc.json", import.meta.url),
      "utf8",
    ),
  ).selected;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  t.after(() => client.clear());
  client.setQueryData(
    [
      "ev-stage-history",
      "NC",
      2026,
      response.revision,
      response.query.as_of,
      "ballots_cast",
      "early_in_person",
      "days_since_opening",
      "retrospective",
      "2016,2018,2020,2022,2024",
    ],
    response,
  );
  const previousLocation = globalThis.location;
  t.after(() => {
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
  });
  const ctx = { query: { state: "NC", cycle: 2026 }, setPage: () => {} };
  globalThis.location = new URL(
    "http://localhost/?ui_forecast_history_alignment=days_since_opening&ui_forecast_history_mode=early_in_person",
  );
  const render = () =>
    renderToString(
      React.createElement(
        QueryClientProvider,
        { client },
        React.createElement(ForecastHistory, {
          ctx,
          call,
          revision: response.revision,
          asOf: response.query.as_of,
        }),
      ),
    ).replace(/<!-- -->/g, "");
  const defaultMarkup = render();
  assert.match(
    defaultMarkup,
    /Show published observations before the method opened/,
  );
  assert.match(
    defaultMarkup,
    /pre-opening observation coordinates are hidden from the default chart window/,
  );
  assert.match(defaultMarkup, /Chart window: Day 0 after method opened/);
  assert.doesNotMatch(defaultMarkup, /Chart window: Day -40/);
  globalThis.location.search += "&ui_forecast_history_preopening=show";
  const expandedMarkup = render();
  assert.match(
    expandedMarkup,
    /Published pre-opening observations are included in the chart/,
  );
  assert.match(expandedMarkup, /Chart window: Day -40 after method opened/);
});

test("final r261 audit renders actual turnout-analogue limits and held-out participation errors without probability claims", async (t) => {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const server = await createServer({
    root,
    configFile: false,
    esbuild: { jsx: "automatic" },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null },
    appType: "custom",
  });
  t.after(() => server.close());
  const { default: Forecasts } = await server.ssrLoadModule(
    "/src/pages/Forecasts.tsx",
  );
  const response = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-research-r261-nc.json", import.meta.url),
      "utf8",
    ),
  );
  const stage = JSON.parse(
    await readFile(
      new URL("./fixtures/ev-stage-r261-nc.json", import.meta.url),
      "utf8",
    ),
  );
  assert.equal(response.backtesting.cases.length, 37);
  assert.equal(response.backtesting.independent_contests, 7);
  assert.equal(response.backtesting.trained_ev_holdout_cases, 0);
  assert.equal(response.selected.evidence.turnout_projection.available, true);
  assert.equal(
    response.selected.evidence.turnout_projection.range_includes_model_error,
    false,
  );
  assert.equal(response.backtesting.turnout.metrics.cases, 7);
  assert.equal(
    response.backtesting.turnout.metrics.independent_state_cycles,
    2,
  );
  const query = {
    state: "NC",
    cycle: 2026,
    baseline: 2022,
    revision: 261,
    as_of: response.as_of,
    time_basis: "reported",
    metric: "ballots_cast",
    mode: "all",
    geography_ids: [],
    alignment: "days_to_election",
    date_window: [],
  };
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(
    ["early-vote-calls", "NC", 2026, 261, response.as_of],
    response,
  );
  client.setQueryData(
    [
      "ev-stage-history",
      "NC",
      2026,
      261,
      response.as_of,
      "ballots_cast",
      "all",
      "days_to_election",
      "retrospective",
      "2016,2018,2020,2022,2024",
    ],
    stage,
  );
  const previousLocation = globalThis.location;
  t.after(() => {
    client.clear();
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
  });
  globalThis.location = new URL("http://localhost/?state=NC&page=forecasts");
  const noop = () => {};
  const bootstrap = JSON.parse(
    await readFile(
      new URL("./fixtures/bootstrap-compact.json", import.meta.url),
      "utf8",
    ),
  );
  const markup = renderToString(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(Forecasts, {
        bootstrap,
        workspace: { revision: 261, query },
        query,
        setQuery: noop,
        setPage: noop,
        inspect: noop,
        notify: noop,
        refresh: noop,
        refreshing: false,
      }),
    ),
  ).replace(/<!-- -->/g, "");
  assert.match(markup, /Conditional turnout analogue · model-run scope/);
  assert.match(
    markup,
    /excludes model error and has no claimed 80% or 95% coverage/,
  );
  assert.match(markup, /Does the turnout analogue survive historical testing/);
  assert.match(markup, /19\.9%/);
  assert.match(markup, /independent state-election outcomes/);
  assert.match(markup, /No win probabilities published/);
  assert.match(markup, /Low forecasting confidence/);
  assert.match(markup, /No validated win probability/);
  assert.doesNotMatch(markup, /NaN|undefined|Infinity|\[object Object\]/);
});
