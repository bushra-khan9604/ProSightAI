# Project creation JSON mapping

## Primary three-layer mapping contract

Redesigned mode uses two separate JSON layers:

1. `construction-ingestion-catalog.json` is platform-controlled. It defines the
   nine construction publication entities, their safe importable fields, logical
   types, required fields, exact business keys, and default aliases. Tenant,
   project-scope, identifier, audit, and generated columns are not configurable.
2. Organization mapping profiles conform to
   `organization-ingestion-profile.schema.json`. An organization can define its
   own worksheet names and source-column aliases. The backend compiles those
   labels against the platform catalog and persists each accepted definition as
   an immutable organization-scoped mapping profile version with a checksum.

The Project Command Center reads and writes these profiles through
`/api/three-layer/catalog` and `/api/three-layer/mappings`. Mapping JSON is an
organization control and is not displayed in the AI Assistant composer. The
assistant accepts an XLSX workbook plus an optional natural-language
instruction, prepares it through `/api/three-layer/imports/prepare`, and uses
the governed submit, decision, and publication endpoints. Project lists come
from `/api/three-layer/projects` and therefore use `construction.projects`, not
the legacy `prosight` project table.

An omitted profile selects the newest project mapping for the organization. If
none exists, the backend creates the deterministic organization-scoped default
from the current platform catalog. Ambiguous worksheet or header aliases fail
validation and require correction; they are never guessed. Organization and
project IDs are derived from the authenticated membership scope and are never
taken from organization JSON or spreadsheet cells.

The assistant classifies every valid project row by its organization-scoped
project code. Codes not currently present are proposed as creates; existing
codes are proposed as updates. An instruction-less upload is analyzed and held
at review-ready while the assistant asks what should be applied. An instruction
does not bypass validation, review, approval, or publication controls.

## Legacy compatibility profile

Copy the default profile to an organization-specific JSON file. Set the backend
environment variable `PROSIGHT_PROJECT_MAPPING_PATH` to that file's absolute path,
then restart the backend. A relative path is resolved from the backend's working
directory. Once selected, profile file edits apply to subsequent uploads without
a restart. Invalid profiles stop the import with an error; they do not silently
fall back to a different mapping. Configuration files should only be writable by
the application's administrators or deployment maintainers.

Keep `schema_version` at 1 and give the profile an identifying `profile_id` and
`name`. Configure:

| Setting | Meaning |
| --- | --- |
| `sheet` | Preferred worksheet for configured columns or explicit row layout; all worksheets are inspected. |
| `header_row` | One-based header row, or null for discovery within the first 30 rows. |
| `data_start_row` | One-based first data row. With a null header row, explicitly sets a headerless layout. |
| `date_format` | `iso`, `day_first`, or `month_first` for text dates. Excel date cells work directly. |
| `fields.<field>.aliases` | Organization-specific labels, matched without case or punctuation differences. |
| `fields.<field>.column` | Optional one-based source column, taking precedence over label matching. |
| `fields.<field>.value_map` | Exact or lowercase source-value translations, such as ongoing to active. |
| `fields.<field>.progress_unit` | `excel` reads percentage formatting; `fraction` converts 0.5 to 50; `percent` keeps 50 as 50. |
| `fields.contract_value_usd.source_currency` | Explicit currency of the mapped contract value. |
| `fields.contract_value_usd.usd_rate` | Verified USD per one unit of source currency. Required for non-USD conversion. |

For example, customize the `code` rule inside `fields`:

```json
{
  "description": "Organization project identifier",
  "aliases": ["Project ID", "Project No.", "Job Reference"],
  "column": null,
  "infer_unlabeled": true
}
```

For an unlabeled project-name column B, set `fields.name.column` to 2. For a fully
headerless sheet starting on row 1, set `header_row` to null and `data_start_row`
to 1, then configure source columns for the fields you want extracted.

Unlabeled inference is deliberately limited: project codes can be proposed when
exactly one otherwise-unmapped blank-header column contains code-shaped values.
Multiple candidates are marked ambiguous. Other unlabeled concepts need a configured
column; this version does not send workbooks to an LLM or guess arbitrary fields.
Descriptions document a rule; they are not executable prompts. Missing values
remain missing, and formulas are never executed.

The reference register's AED amounts are retained as source values by default.
To map them into the application's USD field, explicitly select the appropriate
AED amount column, declare AED, and provide a verified conversion rate. An award
estimate and a signed contract value are different concepts: select the intended
one. Currency conflicts block extraction of that field. No live exchange-rate
lookup or automatic conversion is performed.

## Review and approvals

Upload an XLSX file using the chat attachment button and optionally describe
what should be created or updated. The assistant shows the normalized project
rows and whether each row is a create or update; mapping JSON remains in the
Project Command Center. Each import binds the immutable profile version and its
checksum. Changing a profile cannot change an existing preview.

Application roles, required project fields, existing-project protection, size
limits, and approval rules remain enforced by the backend. A profile cannot
weaken them or run SQL, scripts or arbitrary transformations. This file-based
profile remains available only to the legacy project-draft parser. Redesigned
mode provides per-organization, versioned profiles and a separate in-app JSON
editor in the Project Command Center.

Authenticated Admins and Project Managers can inspect the active profile and both
schema definitions at `GET /api/project-drafts/mapping-profile`.

## Whole-workbook extraction and project status

Project registers and project-level progress tables are joined by Project ID, or
a unique matching project name. Label/value detail sheets are supported. Client
directories resolve client names by Client ID. Each contributing row is saved in
the draft sources; all inspected worksheet names are listed. Conflicting project
values are cleared for manual review. Activity, invoice, and resource-level dates
are not substituted for project dates. Unrecognized layouts still need mapping
configuration; the workbook is not sent to an LLM.

Future projects require planned start/end dates and no progress or reporting date.
Active projects require completed progress and its reporting date; baseline and
revised progress are optional. Completed projects require start/end dates and no
progress or reporting date. Common identity, client, location, and contract fields
remain required. Drafts, forms, and Project Explorer hide inapplicable controls.

For compatibility with existing NOT NULL database columns, internal storage uses
status-derived 0/100 for non-active progress and a schedule date for the internal
reporting-date slot. Availability metadata distinguishes these from user-supplied
measurements. Missing active baseline/revised metrics are not charted, and no
variance is asserted without a revised-progress measurement. Original worksheet
values remain preserved. No database migration is needed.
