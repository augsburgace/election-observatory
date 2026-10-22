import type { OfficeDesk, OfficeRace } from "./officeApi";
import { fmt, partyColor } from "./utils";

export function officeSummaryParagraphs(race: OfficeRace) {
  return [
    race.finding,
    "The participation charts describe the selected election-wide evidence. They do not establish candidate votes in this race.",
    "Senate polling summaries and model estimates are excluded. No verified office-matched polling or market connector is installed for this race.",
  ];
}

export function officeContextSection(
  document: Document,
  race: OfficeRace,
  id: "summary" | "polls",
) {
  const node = document.createElement("section");
  node.id = "section-" + id;
  const title =
    id === "summary"
      ? "Research findings · " + race.name
      : "Office-matched polling coverage";
  const heading = document.createElement("h2");
  heading.textContent = title;
  node.append(heading);
  const paragraphs =
    id === "summary"
      ? officeSummaryParagraphs(race)
      : [
          "No verified polling inventory is installed for this office and race. Senate studies are excluded; unavailable is not a tied race.",
        ];
  for (const text of paragraphs) {
    const p = document.createElement("p");
    p.textContent = text;
    node.append(p);
  }
  return {
    node,
    section: { id, title, paragraphs, figures: [], tables: [], warnings: [] },
  };
}

/** Source-derived report section; all text enters the document as textContent. */
export function officeReportSection(
  document: Document,
  race: OfficeRace,
  desk: OfficeDesk,
) {
  const node = document.createElement("section");
  node.id = "section-office_call";
  const heading = document.createElement("h2");
  heading.textContent = race.name;
  node.append(heading);
  for (const text of [
    race.finding,
    "EV direction not established. No same-stage EV model has been validated for this office. Senate scores and coefficients are not reused.",
    race.historical_reference.description,
  ]) {
    const p = document.createElement("p");
    p.textContent = text;
    node.append(p);
  }
  if (race.latest_result) {
    const title = document.createElement("h3");
    title.textContent = `${race.latest_result.year} actual candidate votes`;
    node.append(title);
    for (const option of race.latest_result.options) {
      const p = document.createElement("p");
      p.textContent = `${option.name} (${option.party || "Unclassified"}): ${fmt(option.votes)} votes · ${option.share_pct?.toFixed(1) ?? "Unavailable"}%`;
      const bar = document.createElement("div");
      bar.style.cssText = `height:12px;background:${partyColor(option.party || "")};width:${option.share_pct ?? 0}%`;
      p.append(bar);
      node.append(p);
    }
  }
  const tables = [
    {
      title: "Historical office results",
      columns: [
        "Year",
        "Contest",
        "Boundary vintage",
        "Actual R minus D pp",
        "Candidate votes",
        "Round",
      ],
      rows: race.history.map((r) => [
        r.year,
        r.contest_name,
        r.boundary_vintage,
        r.margin_pp,
        r.total_votes,
        r.round,
      ]),
    },
    {
      title: "All published candidate options",
      columns: ["Year", "Candidate", "Party", "Votes", "Share %"],
      rows: race.history.flatMap((r) =>
        r.options.map((o) => [r.year, o.name, o.party, o.votes, o.share_pct]),
      ),
    },
  ];
  for (const table of tables) {
    const title = document.createElement("h3");
    title.textContent = table.title;
    node.append(title);
    const element = document.createElement("table"),
      head = document.createElement("thead"),
      row = document.createElement("tr");
    for (const name of table.columns) {
      const cell = document.createElement("th");
      cell.textContent = name;
      row.append(cell);
    }
    head.append(row);
    element.append(head);
    const body = document.createElement("tbody");
    for (const values of table.rows) {
      const row = document.createElement("tr");
      for (const value of values) {
        const cell = document.createElement("td");
        cell.textContent = value == null ? "Unavailable" : String(value);
        row.append(cell);
      }
      body.append(row);
    }
    element.append(body);
    node.append(element);
  }
  for (const warning of race.warnings) {
    const p = document.createElement("p");
    p.className = "warning";
    p.textContent = warning;
    node.append(p);
  }
  const ids = new Set(
    race.history.flatMap((r) => r.source_refs.map((ref) => ref.snapshot_id)),
  );
  const sources = desk.sources
    .filter((s) => ids.has(s.snapshot_id))
    .map((s) => ({
      id: Number(s.snapshot_id),
      url: String(s.url),
      sha256: String(s.sha256),
    }));
  for (const source of sources) {
    const p = document.createElement("p"),
      a = document.createElement("a");
    a.textContent = `Original source snapshot ${source.id}`;
    a.href = source.url;
    p.append(a, ` · SHA-256 ${source.sha256}`);
    node.append(p);
  }
  return {
    node,
    sources,
    section: {
      id: "office_call",
      title: race.name,
      figures: [],
      tables,
      warnings: race.warnings,
    },
  };
}
