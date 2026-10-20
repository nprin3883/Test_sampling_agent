# Edge-case catalog

Each category must end up as a scenario or be declared not applicable with a reason.
Look for them in the code first, the data profile second, the specification third.

| Category | Where to look | Example match |
|---|---|---|
| null | columns with a null rate above zero; COALESCE, NVL, IS NULL branches | `EMAIL is_null` |
| boundary | thresholds in CASE or WHERE; min and max of numeric and date columns | `TOTAL_EUR eq 0`, `TOTAL_EUR gt 10000` |
| duplicate | distinct ratio below one on a natural key; dedup or merge logic | `EMAIL duplicate` |
| tie | ORDER BY or MAX/MIN picking one row among equals; ranking functions | two rows with the same date |
| late_arriving | load timestamp later than business date; reprocessing branches | `LOAD_LAG_DAYS gt 2` |
| corrected | reversal, correction or version columns | `CORRECTION_OF not_null` |
| deleted | soft-delete flags, tombstones, status values meaning removed | `DELETED_FLAG eq Y` |
| business | every remaining branch of the business rules (status mappings, routing) | `STATUS eq S` |

## Risk ranking
- **high**: affects money, legal obligations, or whole records being lost or merged wrongly
- **medium**: affects classification or routing of records
- **low**: cosmetic or rare, and cheap to fix when found late

When unsure, rank higher and say why in the rationale; the Data Architect adjusts it in step 4.

## Gaps you will usually have to declare
- A category with no rule in the code and no occurrence in the profile (cannot be sampled)
- Rare combinations of several categories at once
- Scenarios that only business knowledge reveals (the reviewers add these in step 4)

## Staying inside the limit
Allocate rows per table in proportion to the number of scenarios each table carries, keep a small
reserve, and keep parent rows for every child row you plan to select. Prefer fewer rows covering
more scenarios.
