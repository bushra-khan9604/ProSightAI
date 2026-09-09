# Workforce and deployment imports

ProSight accepts three schema-driven XLSX import types through both the AI Assistant attachment menu and Project Explorer's **Data Import & Review** tab:

- `employees_training`: `Employees` and `Training`
- `attendance_payroll`: `Attendance` and `Payroll`
- `manpower_deployment`: `Direct allocation`, `Subcontract crews`, and `Forecast deployment`

The checked-in JSON Schema documents are in `src/prosight/schemas`. The authenticated `GET /api/attachments/schemas` endpoint returns the runtime record schemas together with the active worksheet-to-field mappings.

## Organization mapping profile

`src/prosight/schemas/workforce-mapping.json` is the editable mapping profile,
validated by `workforce-mapping.schema.json`. Copy it and set
`PROSIGHT_WORKFORCE_MAPPING_PATH` to the copy's absolute path, then restart the
backend. Later profile edits are read on the next upload. Invalid configuration
stops the preview rather than falling back silently.

For each sheet type, configure `aliases`, an optional one-based `header_row`,
and `fields.<field>.aliases`. Headers are discovered within the first 30 rows;
renamed sheets can be identified by their matching columns. A workbook can
contain only Employees, only Attendance, or any supported subset for its action.
Unmatched worksheets are listed in preview warnings.

For unlabeled columns, set `fields.<field>.column` to its one-based position.
For a completely headerless sheet, also set `data_start_row` and leave
`header_row` null. Positional mappings require a matching sheet alias. Ambiguous
columns or sheets stop the preview; sensitive workforce values are not guessed
or sent to an LLM. Field names and validation rules remain fixed so configuration
cannot add arbitrary database columns or SQL.

No reference workbook records are bundled into the mapping profile. The supplied
workbooks were inspected for worksheet names and header structure only.

PostgreSQL deployments must apply the additive workforce migration before starting
the API:

```powershell
python -m prosight.db.manage migrate
python -m prosight.db.manage check
```

The command applies only missing ProSight schema versions and does not import any
rows from the reference workbooks.

## Review and approval flow

1. The server scans the workbook locally and maps recognized headers to strict record fields.
2. Project and employee references must resolve. Duplicate natural keys, invalid dates, invalid numbers, and unexpected formulas stop the preview.
3. Recognized calculated columns are recomputed by the server. Workbook formulas are never executed.
4. The uploader reviews the mapping, record counts, and row sample, then confirms the request.
5. A Project Manager or Planning Engineer confirmation moves the request to the Admin queue. An Admin confirmation can apply immediately.
6. Approval atomically upserts every validated record and writes audit events. Rejected, stale, or unconfirmed requests do not change workforce tables.

The workbook groups are portfolio-scoped because one file may reference several projects. Projects must be created and approved first. Employees must be approved before attendance/payroll or direct-allocation imports unless they are included in the supported employees/training workbook being processed.

Head Office is a supported organizational assignment. Use `HO` in Home project ID
or Project ID for employees, attendance, payroll, direct allocation, subcontract
crews, and deployment forecasts. `Head Office`, `ho`, `H.O.`, and `head-office`
normalize to `HO`. The review explains this assignment, and existing approvals
still apply. No construction project, dates, progress, or project-list entry is
created for HO. All other project references must resolve to existing projects.
