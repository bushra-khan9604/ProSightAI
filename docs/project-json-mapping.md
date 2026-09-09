# Project creation JSON mapping

Excel project creation inspects all worksheets locally and reads
`src/prosight/schemas/project-mapping.json` instead of hardcoded column aliases.
The supplied profile supports the reference Portfolio register and the existing
Projects schema. No new account, API key or database migration is needed.

There are two JSON Schema documents:

- `project-mapping.schema.json` describes the configurable mapping profile.
- `project.schema.json` describes a complete project record. The backend also
  validates schedule ordering and required ISO dates before creation.

## Customize an organization's profile

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

Upload an XLSX file using the chat attachment button and choose Create project
drafts. Expand a draft's **JSON field mappings** section to see source columns,
headers, mapping methods, and the applied JSON profile. Original cells remain
available separately. Each draft stores the complete profile snapshot and its
fingerprint. Changing a profile cannot change an existing preview. A retry using
the same upload ID with a different profile is rejected; select the file again
to prepare a new preview.

Application roles, required project fields, existing-project protection, size
limits, and approval rules remain enforced by the backend. A profile cannot
weaken them or run SQL, scripts or arbitrary transformations. This prototype has
one organization-wide server profile; per-tenant configuration and an in-app
profile editor are not included.

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
