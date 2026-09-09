# Admin project deletion

Project Explorer shows **Delete Project** only to Admin. A native confirmation
dialog requires the exact project code. The DELETE endpoint independently requires
an authenticated admin, even when local compatibility authentication is disabled.

The operation removes the active project's structured records, document metadata,
RAG vectors, ingestion jobs, approvals, notifications, associated audit history,
and managed uploaded originals. PostgreSQL deletes vectors through its document
foreign key. Local Chroma evidence is removed explicitly. Resource caches and the
current browser's project selection and assistant conversation are cleared.

Related portfolio import files, previews, and history are removed too. When an
original workbook contains several projects, that shared source file is removed;
other projects' imported invoice and schedule rows remain, detached from the
removed import history. Manpower rows associated with the deleted project are
removed. The confirmation dialog explains shared source removal.

Deletion refuses active ingestion/import jobs and file paths outside the managed
upload/import roots. Database cleanup is transactional. Files and local Chroma
cannot participate in that transaction: if cleanup fails after removing some
external content, metadata is retained for retry; no successful response is sent.
Missing files are tolerated on retry. Per-project local locks prevent running or
delayed ingestion jobs from restoring deleted evidence. PostgreSQL table locks
serialize cleanup with writes. A hashed deletion marker blocks delayed imports
and reuse of the deleted code; create a replacement project with a new code.

This erases the active application's data, not historical backups, the preserved
SQLite migration snapshot, exported files, or previously downloaded copies.
Multi-instance deployments must use shared managed storage and coordinated workers;
the local-file backend remains intended for a single application host.

Validation: deletion/authorization tests use temporary SQLite databases and files.
Hosted PostgreSQL deletion and pgvector cascade were checked with synthetic rows
inside a rolled-back transaction. Browser verification covered typed confirmation,
successful deletion, and the empty Project Explorer state. No existing project was
deleted while implementing or testing this feature.
