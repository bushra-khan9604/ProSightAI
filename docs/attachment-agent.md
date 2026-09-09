# Attachment and Update Agent

In AI Assistant, use the attachment button beside the chat box. Select an action,
choose the existing project in Analysis context (or select new-project creation),
write an instruction in chat, and send the file. The preview contains the proposed
values, existing values, warnings, and applicable column mappings. It is saved
before any authoritative project update. Reopening the application restores the
operation list for the uploader and Admin.

Supported tools:

- PDF evidence: local extraction, page/chunk preview, optional replacement of an
  approved document, admin approval, then background chunking and embedding.
- Excel: the existing Projects, Manpower, Projects Invoices, and Project Schedule
  schemas. Project workbooks create or update one project; dataset imports are
  restricted to one selected project and cannot overwrite another project's keys.

The selected action is the explicit command. Instructions supply context and are
checked for unsupported destructive requests; arbitrary natural-language SQL is
never generated or executed. Free-form schema inference is not implemented.
For project creation from prose, use the separate [guided workspace](guided-workspace.md).
Known schemas are parsed locally
without an LLM call. Formulas must be exported as values; oversized compressed
workbooks, unsupported schemas, and invalid project references are rejected.

## Confirmation and approval

Every operation starts at `awaiting_confirmation`. Only its authenticated uploader
can confirm it. An Admin uploader can confirm and apply their own preview. Other
members' confirmed updates enter `pending` for Admin review. For this prototype,
all Excel imports require Admin approval, including operational imports. Only
Admin and Project Manager can submit a new project. Members of the same role do
not gain access to each other's attachment previews.

PDF approval also requires explicit permission for external embedding. Unchecked
permission allows local analysis but blocks indexing. Approval does not send the
original PDF to the model: the existing embedding tool sends extracted chunks.
This does not implement a comprehensive DLP classifier; users must not authorize
restricted content for external processing.

Confirmation uses an immutable preview token and checks both the original file
checksum and a database snapshot. Changed inputs produce `stale`, requiring a
new upload/preview. Duplicate active submissions return the same operation.
Database writes, approval status, and import records commit in one transaction;
a failed transaction leaves the preview available. Confirmed uploader and approver
identities are recorded. Admins review attachment requests in AI Assistant; the
legacy generic approval endpoint cannot bypass the saved preview flow.

## PDF lifecycle and recovery

Approved PDF metadata and a durable ingestion job are registered before work is
scheduled. States progress through `indexing` to `completed` or `failed`. Admins
can retry approved PDF indexing without creating another document. The previous
version remains approved until replacement indexing succeeds, then becomes
superseded and is excluded from retrieval. Original versions remain for history.

Workers are still in-process. After a restart, interrupted jobs are marked failed
by the existing ingestion recovery, and the attachment panel offers an Admin retry
for operations left indexing. This is explicit recovery, not a durable distributed
queue. Use a single backend host until shared storage/worker coordination is added.

## Storage and deployment

This implementation uses private, server-managed local files under `data/uploads`;
these files are not served by the frontend static route. Metadata, previews, and
operation states use the existing private PostgreSQL `change_requests` table.
No schema migration, new provider account, or additional API key is needed.
The existing OpenAI API key is required only for approved PDF embeddings.

Supabase Storage migration is not included. The backend host needs durable disk,
restricted filesystem permissions, and appropriate backup/sync controls. The
workspace is currently inside OneDrive; account access and synchronization must
also be considered before storing confidential production data. Rejected previews
and originals are retained as workflow history; define a retention policy before
production use. Project deletion removes related operations and managed originals.

Restart the Python backend and rebuild/refresh the frontend to load the agent.
Existing authenticated Supabase sessions continue to provide identity and role.

## Verification

Automated tests cover ownership and role enforcement, immutable previews, stale
files and database state, duplicate submissions, rollback, real PDF extraction,
failed-index retry, replacement visibility, and API access controls. Hosted
PostgreSQL checks use synthetic operations inside a rolled-back transaction.
Browser verification covers an empty workspace, workbook upload, preview,
confirmation, and appearance of the created project in Project Explorer.
No existing hosted project records were changed by these tests.
