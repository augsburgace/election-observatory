import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import React from "react";
import { renderToString } from "react-dom/server";

test("the actual r592 audited Ohio point is graphical historical context, with no inferred EV advantage", async (t) => {
  const server = await createServer({ root: fileURLToPath(new URL("..", import.meta.url)), configFile: false,
    esbuild: { jsx: "automatic" }, optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: "custom" });
  t.after(() => server.close());
  const { ForecastModelAudit } = await server.ssrLoadModule("/src/components/forecasts/ForecastModelAudit.tsx");
  const call = JSON.parse(await readFile(new URL("./fixtures/ev-call-audited-oh-r592.json", import.meta.url), "utf8"));
  const frozen = JSON.stringify(call);
  const markup = renderToString(React.createElement(ForecastModelAudit, { call })).replace(/<!-- -->/g, "");
  assert.match(markup, /Historical context only/);
  assert.match(markup, /R\s*\+1\.1/);
  assert.match(markup, /0 pp/);
  assert.match(markup, /2018 Senate result/);
  assert.match(markup, /2022 Senate result/);
  assert.match(markup, /different-type outcomes/);
  assert.match(markup, /partisan-primary participation/);
  assert.doesNotMatch(markup, /Outside evidence challenges/);
  assert.equal(JSON.stringify(call), frozen);
});
