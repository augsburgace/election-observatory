// Generated from FastAPI OpenAPI by scripts/generate_api_types.py. Do not edit.

export type CorrectionInput = { "observation_id": number; "replacement": number; "reason": string };

export type DatasetLoadInput = { "state"?: string | null };

export type ExportInput = { "query": ResearchQuery; "format"?: "csv" | "json" | "html" | "pdf" | "zip"; "sections"?: Array<"overview" | "voting" | "geography" | "polls" | "sources"> | null; "title"?: string | null; "note"?: string; "include_notes"?: boolean };

export type HTTPValidationError = { "detail"?: Array<ValidationError> };

export type RefreshInput = { "source_ids"?: Array<string> | null; "state"?: string | null; "include_historical"?: boolean };

export type ReportRequest = { "title"?: string; "template"?: string; "query": ResearchQuery; "results"?: ResultsScope; "context_metric"?: "population" | "median_age" | "median_household_income"; "map_metric"?: "dem_margin_pp" | "total_votes"; "sections"?: Array<ReportSection>; "notes"?: string; "include_notes"?: boolean };

export type ReportSection = { "id": string; "enabled"?: boolean; "caption"?: string };

export type ResearchInput = { "kind": "note" | "view" | "bookmark" | "scenario" | "report" | "correction"; "title": string; "body"?: string; "view"?: { [key: string]: unknown } };

export type ResearchQuery = { "state"?: string; "cycle"?: number; "baseline"?: number; "as_of"?: string | null; "time_basis"?: "reported" | "reconstructed" | "final"; "revision"?: number | null; "metric"?: string; "mode"?: string; "geography_ids"?: Array<string>; "date_window"?: Array<unknown> | null; "category_dimension"?: string | null; "category"?: string | null; "alignment"?: "days_to_election" | "days_since_open" | "days_since_opening" | "voting_opportunities" | "calendar" };

export type ResultsScope = { "year"?: number; "baseline"?: number | null; "office"?: string; "contest_id"?: string | null; "geography_level"?: "state" | "county" | "district" | "municipality" | "precinct"; "geography_ids"?: Array<string>; "offset"?: number; "limit"?: number };

export type ValidationError = { "loc": Array<string | number>; "msg": string; "type": string; "input"?: unknown; "ctx"?: Record<string, unknown> };
