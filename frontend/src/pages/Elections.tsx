import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarDays,
  ExternalLink,
  Search,
  Vote,
} from "lucide-react";
import type { AppContext } from "../types";
import { atlasApi } from "../atlasApi";
import { DatasetDownload } from "../components/DownloadStatus";
import HistoricalExplorer from "../components/HistoricalExplorer";
import { openEntity } from "../components/EntityInspector";
import {
  Badge,
  Empty,
  Loading,
  Notice,
  Panel,
  Select,
  Stat,
} from "../components/ui";
import { fmt, human, stateName } from "../utils";
export default function Elections(ctx: AppContext) {
  const [search, setSearch] = useState(""),
    [section, setSection] = useState("contests");
  const catalog = useQuery({
    queryKey: ["atlas", "datasets", ctx.query.state],
    queryFn: () => atlasApi.datasets(ctx.query.state),
  });
  const states = useQuery({
    queryKey: ["atlas", "states"],
    queryFn: atlasApi.states,
  });
  const [offset, setOffset] = useState(0);
  useEffect(
    () => setOffset(0),
    [ctx.query.state, ctx.resultYear, ctx.resultOffice, search],
  );
  const result = useQuery({
    queryKey: [
      "atlas",
      "election-catalog",
      ctx.query.state,
      ctx.resultYear,
      ctx.resultOffice,
      ctx.query.revision,
      search,
      offset,
    ],
    queryFn: () =>
      atlasApi.contests({
        state: ctx.query.state,
        year: ctx.resultYear || 2024,
        office: ctx.resultOffice || "PRESIDENT",
        revision: ctx.query.revision,
        q: search,
        limit: 50,
        offset,
      }),
  });
  const state = states.data?.states.find((s) => s.code === ctx.query.state);
  const datasets = (catalog.data?.datasets || []).filter((d) =>
    `${d.title} ${d.producer} ${d.offices.join(" ")}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <>
      <div className="page-intro">
        <div>
          <h2>Every election has a research trail.</h2>
          <p>
            Find verified contests, ballot options, original producers, and the
            historical records available for each place.
          </p>
        </div>
        <Badge tone="violet">{stateName(ctx.query.state)}</Badge>
      </div>
      <div className="catalog-scope">
        <Select
          label="Office"
          value={ctx.resultOffice || "PRESIDENT"}
          onChange={(v) => ctx.setResultOffice?.(v)}
          options={[
            ...new Set([
              "PRESIDENT",
              "US SENATE",
              "US HOUSE",
              ...(state?.offices || []),
              "GOVERNOR",
              "STATE SENATE",
              "STATE HOUSE",
              "JUDICIAL",
              "LOCAL",
              "BALLOT MEASURE",
            ]),
          ].map((v) => ({ value: v, label: human(v) }))}
        />
        <div className="segmented">
          {["contests", "datasets", "results"].map((s) => (
            <button
              key={s}
              className={section === s ? "active" : ""}
              onClick={() => setSection(s)}
            >
              {human(s)}
            </button>
          ))}
        </div>
        <div className="search-field">
          <Search size={15} />
          <input
            aria-label="Search election datasets"
            placeholder="Search datasets and offices…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      {section === "results" ? (
        <HistoricalExplorer {...ctx} embedded />
      ) : section === "contests" ? (
        <>
          <div className="stat-grid">
            <Stat
              label="Loaded historical result records"
              value={fmt(state?.result_count)}
              detail={
                state?.years?.length
                  ? `${Math.min(...state.years)}–${Math.max(...state.years)} verified dataset range`
                  : "Verified years appear after collection"
              }
              icon={<Vote size={20} />}
            />
            <Stat
              label="Available offices"
              value={state?.offices?.length || 0}
              detail={
                state?.offices?.slice(0, 4).map(human).join(" · ") +
                  (state?.offices && state.offices.length > 4
                    ? ` · +${state.offices.length - 4} more in the office selector`
                    : "") || "See source availability below"
              }
              accent="violet"
              icon={<CalendarDays size={20} />}
            />
          </div>
          <Panel
            title={`${ctx.resultYear || 2024} contests · ${stateName(ctx.query.state)}`}
            subtitle="Contest identity preserves office, district, election type, and round."
          >
            {result.isPending ? (
              <Loading />
            ) : result.data?.contests?.length ? (
              <div className="contest-list">
                {result.data.contests.map((c) => (
                  <details key={c.id} open={result.data!.contests.length === 1}>
                    <summary>
                      <span>
                        <b>
                          {c.name ||
                            c.title ||
                            human(c.office || ctx.resultOffice)}
                        </b>
                        <small>
                          {c.year || ctx.resultYear} ·{" "}
                          {human(c.election_type || "general")}{" "}
                          {c.district ? `· District ${c.district}` : ""}
                        </small>
                      </span>
                      <ArrowRight size={16} />
                    </summary>
                    <div className="contest-body">
                      <dl>
                        {Object.entries(c)
                          .filter(
                            ([k, v]) =>
                              !["id", "options", "name", "title"].includes(k) &&
                              typeof v !== "object",
                          )
                          .map(([k, v]) => (
                            <div key={k}>
                              <dt>{human(k)}</dt>
                              <dd>{String(v ?? "Not published")}</dd>
                            </div>
                          ))}
                      </dl>
                      {c.options?.map((o) => (
                        <div className="contest-option" key={o.id}>
                          <b>{o.name}</b>
                          <Badge>{o.party || "Ballot option"}</Badge>
                          <span>{fmt(o.votes)} votes</span>
                        </div>
                      ))}
                      <button
                        className="button secondary"
                        onClick={() => openEntity(c.id)}
                      >
                        Inspect ballot identities
                      </button>
                      <button
                        className="button primary"
                        onClick={() => {
                          const p = new URLSearchParams(location.search);
                          p.set("ui_result_contest", c.id);
                          p.set(
                            "ui_result_grain",
                            c.district && c.district !== "STATEWIDE"
                              ? "district"
                              : "state",
                          );
                          history.replaceState(null, "", `?${p}`);
                          window.dispatchEvent(new Event("observatory-layout"));
                          setSection("results");
                        }}
                      >
                        Explore contest results
                        <ArrowRight size={14} />
                      </button>
                    </div>
                  </details>
                ))}
              </div>
            ) : (
              <Empty title="No loaded contest matches this office and year">
                The dataset inventory explains coverage. Select an available
                office or load a verified source below.
              </Empty>
            )}
            {(result.data?.total || 0) > 50 && (
              <div className="table-pagination">
                <button
                  className="button small secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 50))}
                >
                  Previous
                </button>
                <span>
                  {offset + 1}–{Math.min(offset + 50, result.data?.total || 0)}{" "}
                  of {result.data?.total} contests
                </span>
                <button
                  className="button small secondary"
                  disabled={offset + 50 >= (result.data?.total || 0)}
                  onClick={() => setOffset(offset + 50)}
                >
                  Next
                </button>
              </div>
            )}
          </Panel>
          <Panel title="Verified dataset availability">
            <div className="dataset-catalog">
              {datasets.map((d) => (
                <DatasetDownload
                  key={d.id}
                  dataset={d}
                  state={ctx.query.state}
                />
              ))}
            </div>
          </Panel>
        </>
      ) : (
        <Panel
          title="Original evidence and documented data bridges"
          subtitle="Availability is dataset-specific. Offices without a verified collection remain explicitly unavailable."
        >
          {catalog.isPending ? (
            <Loading />
          ) : datasets.length ? (
            <div className="dataset-catalog">
              {datasets.map((d) => (
                <section key={d.id}>
                  <DatasetDownload dataset={d} state={ctx.query.state} />
                  <div className="dataset-details">
                    <p>
                      {d.offices.map(human).join(" · ")} ·{" "}
                      {d.geography_levels.join(", ")} ·{" "}
                      {d.years.length
                        ? `${Math.min(...d.years)}–${Math.max(...d.years)}`
                        : "Year range not established"}
                    </p>
                    <p>
                      {d.license ||
                        "License and use conditions shown in original publication"}
                    </p>
                    <a href={d.url} target="_blank" rel="noreferrer">
                      Original publication
                      <ExternalLink size={12} />
                    </a>
                    {d.warnings.map((w, i) => (
                      <Notice key={i}>{w}</Notice>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : (
            <Empty title="No verified dataset matches">
              Try another office or search term. This catalog records actual
              evidence, without inventing unavailable local results.
            </Empty>
          )}
        </Panel>
      )}
      <Notice>
        Participation belongs to an election; candidate and ballot-measure
        results belong to a particular contest. Historical datasets provide
        context and do not identify how current early voters voted.
      </Notice>
    </>
  );
}
