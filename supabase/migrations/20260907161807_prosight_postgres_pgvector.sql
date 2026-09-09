-- ProSight single-organization persistence migration. Apply once, transactionally.
-- Private server-only schema; tenant membership/RLS is a separate migration.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
DO $$
DECLARE extension_schema text; extension_version text;
BEGIN
    SELECT n.nspname,e.extversion INTO extension_schema,extension_version
    FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector';
    IF extension_schema <> 'extensions' THEN
        RAISE EXCEPTION 'Existing vector extension is outside extensions; review before migrating';
    END IF;
    IF string_to_array(extension_version,'.')::int[] < ARRAY[0,8,0] THEN
        RAISE EXCEPTION 'pgvector 0.8 or newer is required for filtered iterative HNSW search';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='prosight_backend') THEN
        RAISE EXCEPTION 'Role prosight_backend already exists; review existing installation before applying';
    END IF;
    CREATE ROLE prosight_backend NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    EXECUTE format('GRANT prosight_backend TO %I',current_user);
END $$;
CREATE SCHEMA prosight;
SET LOCAL search_path = prosight,extensions,pg_catalog;
REVOKE ALL ON SCHEMA prosight FROM PUBLIC;
GRANT USAGE ON SCHEMA prosight,extensions TO prosight_backend;

CREATE TABLE audit_events (
                        id TEXT PRIMARY KEY,
                        request_id TEXT,
                        actor_role TEXT NOT NULL,
                        action TEXT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        before_json TEXT,
                        after_json TEXT,
                        created_at TEXT NOT NULL
                    );

CREATE TABLE change_requests (
                        id TEXT PRIMARY KEY,
                        action TEXT NOT NULL,
                        project_code TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        preview TEXT NOT NULL,
                        status TEXT NOT NULL,
                        requested_by TEXT NOT NULL,
                        decided_by TEXT,
                        created_at TEXT NOT NULL,
                        decided_at TEXT
                    );

CREATE TABLE documents (
                        id TEXT PRIMARY KEY,
                        project_code TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        kind TEXT NOT NULL CHECK(kind IN ('pdf','xlsx')),
                        checksum TEXT NOT NULL,
                        stored_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL, reporting_date TEXT, effective_date TEXT, date_status TEXT NOT NULL DEFAULT 'pending', approval_status TEXT NOT NULL DEFAULT 'awaiting_approval', index_status TEXT NOT NULL DEFAULT 'not_indexed', revision TEXT, security_classification TEXT NOT NULL DEFAULT 'internal', approved_by TEXT, approved_at TEXT,
                        UNIQUE(project_code, checksum)
                    );

CREATE TABLE ingestion_jobs (
                        id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress INTEGER NOT NULL DEFAULT 0,
                        message TEXT,
                        change_request_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

CREATE TABLE manpower_assignments (
                        emp_code TEXT PRIMARY KEY,
                        current_project_code TEXT NOT NULL,
                        mobilized_project_code TEXT,
                        name TEXT NOT NULL,
                        designation TEXT,
                        department TEXT,
                        category TEXT,
                        current_location TEXT,
                        allocation TEXT,
                        status TEXT,
                        leave_balance DOUBLE PRECISION,
                        employee_id TEXT,
                        period_start TEXT,
                        period_end TEXT,
                        capacity_hours DOUBLE PRECISION,
                        planned_hours DOUBLE PRECISION,
                        actual_hours DOUBLE PRECISION,
                        billable_hours DOUBLE PRECISION,
                        leave_hours DOUBLE PRECISION,
                        allocation_percent DOUBLE PRECISION,
                        billing_rate DOUBLE PRECISION,
                        cost_rate DOUBLE PRECISION,
                        revision TEXT,
                        approval_status TEXT NOT NULL DEFAULT 'approved',
                        data_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        import_id TEXT NOT NULL
                    );

CREATE TABLE notifications (
                        id TEXT PRIMARY KEY,
                        recipient_role TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        project_code TEXT NOT NULL,
                        change_request_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        read_at TEXT,
                        created_at TEXT NOT NULL,
                        UNIQUE(recipient_role, event_type, change_request_id)
                    );

CREATE TABLE portfolio_import_jobs (
                        id TEXT PRIMARY KEY,
                        import_id TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL,
                        progress INTEGER NOT NULL,
                        message TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

CREATE TABLE portfolio_imports (
                        id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        checksum TEXT NOT NULL,
                        stored_path TEXT NOT NULL,
                        uploaded_by TEXT NOT NULL,
                        status TEXT NOT NULL,
                        summary_json TEXT,
                        error_message TEXT,
                        created_at TEXT NOT NULL,
                        completed_at TEXT
                    , dataset TEXT, project_code TEXT);

CREATE TABLE project_invoices (
                        job_number TEXT NOT NULL,
                        draft_invoice_number TEXT NOT NULL,
                        project_code TEXT NOT NULL,
                        levels TEXT,
                        status TEXT,
                        approval_status TEXT,
                        payment_status TEXT,
                        risk_profile TEXT,
                        invoice_value_usd NUMERIC(20,4) NOT NULL,
                        invoice_value_aed DOUBLE PRECISION,
                        submission_date TEXT,
                        expected_remittance_date TEXT,
                        data_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        import_id TEXT NOT NULL,
                        PRIMARY KEY(job_number, draft_invoice_number)
                    );

CREATE TABLE project_schedule_activities (
                        project_code TEXT NOT NULL,
                        activity_id TEXT NOT NULL,
                        activity_name TEXT NOT NULL,
                        start_date TEXT NOT NULL,
                        finish_date TEXT NOT NULL,
                        original_duration INTEGER NOT NULL,
                        import_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(project_code, activity_id)
                    );

CREATE TABLE projects (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('completed','active','future')),
                    client TEXT NOT NULL,
                    location TEXT NOT NULL,
                    contract_value_usd DOUBLE PRECISION NOT NULL,
                    planned_start TEXT NOT NULL,
                    planned_finish TEXT NOT NULL,
                    revised_finish TEXT,
                    reporting_date TEXT NOT NULL,
                    baseline_progress DOUBLE PRECISION NOT NULL,
                    revised_progress DOUBLE PRECISION NOT NULL,
                    actual_progress DOUBLE PRECISION NOT NULL,
                    payload TEXT NOT NULL
                );

CREATE TABLE seed_migrations (
                        migration_key TEXT PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    );

CREATE TABLE sessions (
                        id TEXT PRIMARY KEY,
                        token_hash TEXT NOT NULL UNIQUE,
                        user_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        revoked_at TEXT
                    );

CREATE TABLE users (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        display_name TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        failed_login_count INTEGER NOT NULL DEFAULT 0,
                        locked_until TEXT,
                        created_at TEXT NOT NULL,
                        last_login_at TEXT
                    );

CREATE INDEX idx_change_requests_status_created
                        ON change_requests(status, created_at DESC);

CREATE INDEX idx_invoices_project
                        ON project_invoices(project_code);

CREATE INDEX idx_manpower_department ON manpower_assignments(department);

CREATE INDEX idx_manpower_employee ON manpower_assignments(employee_id);

CREATE INDEX idx_manpower_period ON manpower_assignments(period_start, period_end);

CREATE INDEX idx_manpower_project
                        ON manpower_assignments(current_project_code);

CREATE INDEX idx_notifications_role_created
                        ON notifications(recipient_role, created_at DESC);

CREATE INDEX idx_schedule_project_start
                        ON project_schedule_activities(project_code, start_date);

CREATE INDEX idx_sessions_token
                        ON sessions(token_hash);


ALTER TABLE documents ADD CONSTRAINT documents_id_project_unique UNIQUE(id,project_code);
CREATE TABLE document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    project_code TEXT NOT NULL,
    body TEXT NOT NULL CHECK(length(body)>0),
    metadata JSONB NOT NULL,
    embedding extensions.vector(1536) NOT NULL,
    embedding_model TEXT NOT NULL,
    search_text TSVECTOR GENERATED ALWAYS AS (to_tsvector('english'::regconfig,body)) STORED,
    FOREIGN KEY(document_id,project_code) REFERENCES documents(id,project_code) ON DELETE CASCADE,
    CHECK(metadata->>'approval_status' IS NOT DISTINCT FROM 'approved'),
    CHECK(metadata->>'document_id' IS NOT DISTINCT FROM document_id),
    CHECK(metadata->>'project_code' IS NOT DISTINCT FROM project_code)
);
CREATE INDEX chunks_project_document ON document_chunks(project_code,document_id);
CREATE INDEX chunks_document ON document_chunks(document_id);
CREATE INDEX chunks_text ON document_chunks USING gin(search_text);
CREATE INDEX chunks_embedding ON document_chunks USING hnsw(embedding extensions.vector_cosine_ops);
CREATE INDEX documents_project_visibility ON documents(project_code,approval_status,index_status,status);
CREATE INDEX ingestion_jobs_document ON ingestion_jobs(document_id);
CREATE INDEX ingestion_jobs_change ON ingestion_jobs(change_request_id);
CREATE INDEX invoices_project ON project_invoices(project_code);
CREATE INDEX manpower_project ON manpower_assignments(current_project_code);
CREATE TABLE schema_version(version INTEGER PRIMARY KEY, installed_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO schema_version(version) VALUES (1);

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON audit_events TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE change_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE change_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON change_requests TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON documents TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON ingestion_jobs TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE manpower_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE manpower_assignments FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON manpower_assignments TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON notifications TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE portfolio_import_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_import_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON portfolio_import_jobs TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE portfolio_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_imports FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON portfolio_imports TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE project_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_invoices FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON project_invoices TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE project_schedule_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_schedule_activities FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON project_schedule_activities TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON projects TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE seed_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE seed_migrations FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON seed_migrations TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON sessions TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON users TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON document_chunks TO prosight_backend USING (true) WITH CHECK (true);

ALTER TABLE schema_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_version FORCE ROW LEVEL SECURITY;
CREATE POLICY backend_access ON schema_version TO prosight_backend USING (true) WITH CHECK (true);

GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA prosight TO prosight_backend;
REVOKE ALL ON ALL TABLES IN SCHEMA prosight FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA prosight REVOKE ALL ON TABLES FROM PUBLIC;
DO $$
DECLARE api_role text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=api_role) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA prosight FROM %I',api_role);
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA prosight FROM %I',api_role);
        END IF;
    END LOOP;
END $$;
