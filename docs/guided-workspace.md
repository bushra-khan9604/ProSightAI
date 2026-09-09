# Guided workspace and project creation

When there are no approved projects, Command Center and Project Explorer show a
guided entry point. Admins and Project Managers can describe their first project
or open the existing workbook workflow. Planning Engineers see guidance to wait
for an approved project.

AI Assistant has one chat composer. Its first message introduces ProSight AI and
invites users to describe a project or upload an Excel register. Give the name, code, client,
location, status, USD contract value, schedule, reporting date and progress. The
assistant asks for missing information; all fields remain editable. Natural
language interpretation requires the displayed AI consent checkbox. Manual field
entry works without an AI provider. Only the description and current draft are
sent to the configured provider, with response storage disabled.

Review and save any field edits before confirming. An Admin's confirmation creates
the project. A Project Manager's confirmation saves a pending request; an Admin
opens AI Assistant, expands the saved draft message and approves or rejects it. Drafts
are stored in the database and can be reopened after refresh. They do not appear
in the live portfolio until creation succeeds.

Authenticated backend checks enforce ownership and roles. Revision checks reject
stale previews, duplicate project codes cannot overwrite existing projects, and
creation plus approval is transactional. Repeated confirmation is idempotent.
The model only extracts structured fields; it cannot execute SQL or create a
project directly.

No new account or database migration is required. Natural-language extraction uses
the existing configured OpenAI model and API key. Restart the backend and refresh
the frontend after building with `pnpm --dir frontend build`.

Use the attachment button beside the chat box to upload an XLSX register. The
whole workbook is inspected locally, including title rows before the column headers.
One or multiple project rows become separate initial drafts, with a limit of
100 projects per upload. Review each draft independently. Uploading never creates
a live project. Retrying the same upload request restores the same drafts.

The Portfolio sheet in `01_Company_and_Project_Registers.xlsx` is supported:
Project ID, Project name, Status, Location, Start date, Baseline finish and
Forecast finish map to project fields. Original values, source filename, sheet
and row remain available in each draft. Client IDs do not become client names.
AED amounts are preserved as source values; a verified USD contract value is
required by the application's current schema. Unstated reporting dates and
progress remain missing. Formulas are preserved as source text and never executed;
verified values must be entered before confirmation. Project-level details from other sheets can enrich drafts through matching project identifiers or client IDs. See project-json-mapping.md for status-specific requirements.

Existing PDF and structured update workflows use the same attachment button, with
an action selector after file selection and inline approval previews. PDF version
replacement and external-embedding consent are retained.

## Chat lifecycle

Creating or rejecting a project removes its preview and associated assistant
messages from chat, preserving user prompts. Shared upload summaries are also cleared when one of their
projects finishes; other unfinished project cards stay available. Completed and
rejected attachment cards are hidden as well. Backend records and audit history
are retained. Completed attachment ingestion replaces its assistant progress
responses with “Upload/ingestion complete.” once, preserving the user's upload
prompt. Pending approval, indexing, and failure are not reported as completion.

New chat clears messages, visible workflow cards, the selected draft, attachments,
unsent input, processing consent, and project context. Background polling cannot
restore old cards. The clean view is remembered for this signed-in user in the
current browser tab, including page refreshes. Only workflow IDs and visibility
settings are stored in session storage, not file contents or messages.

To deliberately recover pending work, type **show saved drafts** or **review
pending requests**, or open its review link from Notifications.
