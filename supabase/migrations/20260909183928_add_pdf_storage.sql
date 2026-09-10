-- Persist approved PDF originals in a private Supabase Storage bucket.
SET LOCAL search_path = prosight, extensions, pg_catalog;

ALTER TABLE documents
    ADD COLUMN storage_bucket TEXT,
    ADD COLUMN storage_object_path TEXT,
    ADD COLUMN storage_uploaded_at TIMESTAMPTZ;

ALTER TABLE documents ADD CONSTRAINT documents_storage_reference_complete CHECK (
    (storage_bucket IS NULL AND storage_object_path IS NULL AND storage_uploaded_at IS NULL)
    OR
    (storage_bucket IS NOT NULL AND storage_object_path IS NOT NULL AND storage_uploaded_at IS NOT NULL)
);

CREATE UNIQUE INDEX documents_storage_object_unique
    ON documents(storage_bucket, storage_object_path)
    WHERE storage_bucket IS NOT NULL AND storage_object_path IS NOT NULL;

-- Private, PDF-only, and aligned with the application's existing 20 MB limit.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('prosight-pdfs', 'prosight-pdfs', false, 20971520, ARRAY['application/pdf'])
ON CONFLICT (id) DO UPDATE SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

INSERT INTO schema_version(version) VALUES (3);
