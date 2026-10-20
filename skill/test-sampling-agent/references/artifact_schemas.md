# Artifact schemas

JSON, UTF-8. Fields marked * are required. The checker enforces them; this page explains them.

## request_pack.json (step 1)
- `migration_id`*, `ticket_ref`*, `specification_ref`*
- `acceptance_criteria`* list of text
- `source_definitions`* and `target_definitions`*: list of `{table, attributes[{name, ...}], keys[]}`
- `environments`* e.g. `{source, target}`
- `constraints`*: `max_sample_rows`* positive integer, `data_handling_rules`* non-empty list, optional `max_cost_eur`
- `source_code_refs`* list of files or locations; `[]` is allowed and triggers reduced confidence

## sampling_brief.json (step 2)
- `status`*: `needs_answers` or `validated`
- `code_available`* boolean, `confidence`*: `normal` or `reduced`
- `inputs_used`*: `{schemas, profiling_stats, source_code, raw_records}` booleans; `raw_records` must be false
- `business_rules`*: list of `{id, description, source_ref}`
- `open_questions`: list of `{id, question, blocking, answered, answer?}`

## sampling_spec.json (steps 3 and 4)
- `scenarios`*: ranked, high risk first. Each: `id`, `title`, `category`, `risk`, `covered`, `rationale`, `rule_refs[]`; a covered scenario also needs `match` and `extraction_query`.
  - `category`: null, boundary, duplicate, tie, late_arriving, corrected, deleted, business
  - `risk`: high, medium, low
- `coverage_gaps`: `{scenario_id, reason}` for every scenario with `covered: false`
- `edge_categories_not_applicable`: `{category: reason}`
- `sampling_strategy`*: `max_sample_rows`* (never above the request limit), `per_table_allocation`* `{table: rows}`, `relationships` list of `{parent, child, key}` (required when several tables are sampled)
- `approval`*: `status` draft, approved or rejected. When approved: `approved_by {data_architect, data_owner}` (named humans), `masking_confirmed: true`, `gaps_accepted: true`, `date`

### match predicate
`{"table": "CUSTOMER", "conditions": [{"field": "EMAIL", "op": "is_null"}]}`; all conditions must hold on the same row.
Operators: `is_null`, `not_null`, `eq`, `ne`, `in` (value is a list), `lt`, `lte`, `gt`, `gte`, `between` (value is `[low, high]`), `duplicate` (value occurs more than once in the sample table).

## coverage_report.json (step 5)
Produced by `verify`, never written by hand: `ticket_ref`, `spec_status`, `total_rows`, `rows_by_table`, `scenario_coverage[{scenario_id, matched_rows}]`, `referential_integrity`, `volume_limit`, `summary {covered, missed, declared_gaps}`.

## Finding codes
| Prefix | Meaning |
|---|---|
| REQ | request pack incomplete (REQ-005 is a warning: no code) |
| BRF | brief: raw records, unanswered blocking question, rule without evidence, confidence |
| SPC | specification: fields, ranking, categories, gaps, limits, relationships, read-only queries, approval (SPC-011), not yet approved (SPC-013) |
| COV | report: volume, missed scenario, orphans, unapproved spec, numbers not reproducible (COV-008) |
| DAT | personal data in an artifact (DAT-001) or an unmasked extracted sample (DAT-002); heuristic, not a substitute for the data-handling rules |
