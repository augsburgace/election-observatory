import { originalDocumentHref } from "../publicData";
import { useViewOption } from "../viewState";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bookmark, FileSearch } from "lucide-react";
import type { AppContext } from "../types";
import { atlasApi, type PlaceSeries, type Results } from "../atlasApi";
import { api } from "../api";
import { Badge, Empty, Loading, Notice, Panel } from "../components/ui";
import {
  VoteDistribution,
  PlaceTrajectories,
  HistoricalShareChart,
} from "../components/ResearchCharts";
import HistoricalExplorer from "../components/HistoricalExplorer";
import { fmt, stateName, human } from "../utils";
export default function PlaceDossier(ctx: AppContext) {
  const id =
    new URLSearchParams(location.search).get("ui_place") ||
    new URLSearchParams(location.search).get("ui_entity") ||
    ctx.query.geography_ids[0] ||
    "";
  const [historyOffset, setHistoryOffset] = useViewOption<string>(
    "place_history_offset",
    "0",
  );
  const q = useQuery({
    queryKey: [
      "atlas",
      "place",
      id,
      ctx.query.state,
      ctx.query.revision ?? ctx.workspace.revision,
      ctx.resultYear,
      ctx.resultOffice,
      ctx.workspace.query,
      historyOffset,
    ],
    queryFn: () =>
      atlasApi.place(
        id,
        ctx.query.state,
        ctx.query.revision ?? ctx.workspace.revision,
        ctx.resultYear,
        ctx.resultOffice,
        ctx.workspace.query,
        Number(historyOffset) || 0,
      ),
    enabled: !!id,
  });
  const data = q.data || {},
    versions = (data.versions || []) as Record<string, unknown>[],
    place = versions.at(-1) || {},
    history = (data.history || []) as Results[],
    latest = history[0],
    focus = latest?.geographies[0],
    participation = (data.participation || {}) as Record<string, unknown>,
    series = (participation.places || []) as PlaceSeries[],
    context = (data.context || {}) as Record<string, unknown>,
    estimates = (context.estimates || []) as Record<string, unknown>[],
    notes = (data.warnings || []) as string[];
  const historyPoints = history.map((r) => ({
    year: r.query.year,
    ...r.summary,
  }));
  const historyPage = (data.history_page || {}) as {
    total?: number;
    offset?: number;
    limit?: number;
    has_more?: boolean;
  };
  async function bookmark() {
    try {
      await api.saveResearch({
        kind: "bookmark",
        title: String(place.name || id) + " · place dossier",
        view: {
          query: ctx.workspace.query,
          page: "place",
          layout: { ui_place: id },
        },
      });
      ctx.notify("Place profile bookmarked.");
    } catch (e) {
      ctx.notify((e as Error).message);
    }
  }
  return (
    <>
      <button className="text-button" onClick={() => ctx.setPage("atlas")}>
        <ArrowLeft size={14} />
        Back to atlas
      </button>
      {!id ? (
        <Empty title="Choose a place on the atlas">
          Select a reporting area to open its durable research profile.
        </Empty>
      ) : q.isPending ? (
        <Loading label="Opening place evidence…" />
      ) : q.isError ? (
        <Notice tone="warning">{q.error.message}</Notice>
      ) : (
        <>
          <div className="page-intro">
            <div>
              <h2>{String(place.name || focus?.name || id)}</h2>
              <p>
                {stateName(ctx.query.state)} ·{" "}
                {String(place.level || "Reporting area")} · {id}
              </p>
            </div>
            <button className="button secondary" onClick={bookmark}>
              <Bookmark size={14} />
              Bookmark place
            </button>
          </div>
          <div className="place-dossier-facts">
            <span>{id}</span>
            <span>
              Published geography vintages{" "}
              {versions.map((v) => String(v.vintage)).join(", ") ||
                "Not established"}
            </span>
            <Badge tone="teal">Published aggregate evidence</Badge>
          </div>
          <div className="chart-grid">
            <Panel
              title="Reported participation over time"
              subtitle="Separate series preserve the place and source chronology."
            >
              <PlaceTrajectories
                series={series}
                selected={series.map((s) => s.id)}
                observations={ctx.workspace.observations}
              />
            </Panel>
            <Panel
              title="Historical candidate shares"
              subtitle="Published returns for this place; boundary changes remain explicit."
            >
              <HistoricalShareChart history={historyPoints} />
            </Panel>
            <Panel
              title="Latest loaded historical contest"
              subtitle={`${String(latest?.query.year || "")} · ${human(String(latest?.query.office || ""))}`}
            >
              {focus ? (
                <VoteDistribution rows={[focus]} />
              ) : (
                <Empty title="No historical result is loaded for this place">
                  Use the dataset catalog to inspect source availability.
                </Empty>
              )}
            </Panel>
            <Panel title="Resident population context">
              <div className="context-estimate-grid">
                {estimates.map((e, i) => (
                  <div key={i}>
                    <span>{human(String(e.metric))}</span>
                    <strong>{fmt(e.estimate)}</strong>
                    <small>
                      {String(e.period_start || "").slice(0, 4)}–
                      {String(e.period_end || "").slice(0, 4)}{" "}
                      {e.moe != null ? `· ±${fmt(e.moe)} (90%)` : ""}
                    </small>
                  </div>
                ))}
              </div>
              <p className="muted">
                Resident population includes nonvoters and is not the observed
                composition of current voters.
              </p>
            </Panel>
          </div>
          <Panel title="Election-by-election record">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Election</th>
                    <th>Contest</th>
                    <th>Candidate / option votes</th>
                    <th>Democratic share</th>
                    <th>Republican share</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((r, i) => (
                    <tr key={i}>
                      <td>{String(r.query.year)}</td>
                      <td>{human(String(r.query.office))}</td>
                      <td className="numeric">{fmt(r.summary.total_votes)}</td>
                      <td className="dem-value">
                        {r.summary.dem_share_pct == null
                          ? "—"
                          : fmt(r.summary.dem_share_pct, 1) + "%"}
                      </td>
                      <td className="rep-value">
                        {r.summary.rep_share_pct == null
                          ? "—"
                          : fmt(r.summary.rep_share_pct, 1) + "%"}
                      </td>
                      <td>
                        {r.sources[0]?.id != null && (
                          <a
                            className="text-button"
                            href={originalDocumentHref(r.sources[0])}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <FileSearch size={13} />
                            Original record
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(historyPage.has_more || Number(historyOffset) > 0) && (
              <div className="table-pagination">
                <button
                  className="button small secondary"
                  disabled={Number(historyOffset) === 0}
                  onClick={() =>
                    setHistoryOffset(
                      String(Math.max(0, Number(historyOffset) - 8)),
                    )
                  }
                >
                  Newer elections
                </button>
                <span>{historyPage.total} observed election years</span>
                <button
                  className="button small secondary"
                  disabled={!historyPage.has_more}
                  onClick={() =>
                    setHistoryOffset(String(Number(historyOffset) + 8))
                  }
                >
                  Earlier elections
                </button>
              </div>
            )}
          </Panel>
          <Panel title="Boundary and identity trail">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Published name</th>
                    <th>Geographic level</th>
                    <th>Vintage</th>
                    <th>Source context</th>
                  </tr>
                </thead>
                <tbody>
                  {versions.map((v, i) => (
                    <tr key={i}>
                      <td>{String(v.name)}</td>
                      <td>{String(v.level)}</td>
                      <td>{String(v.vintage)}</td>
                      <td>
                        {String(
                          (v.payload as Record<string, unknown>)
                            ?.boundary_match || "",
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <HistoricalExplorer {...ctx} embedded />
          {notes.map((w, i) => (
            <Notice key={i}>{w}</Notice>
          ))}
        </>
      )}
    </>
  );
}
