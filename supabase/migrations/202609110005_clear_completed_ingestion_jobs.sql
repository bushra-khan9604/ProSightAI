-- A ready document is the durable result. Successful ingestion jobs are transient
-- progress records and are removed atomically when publishing the document.

create or replace function public.complete_document_ingestion(
  target_document_id uuid,
  target_job_id uuid,
  chunk_count integer
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if chunk_count < 1 or (
    select count(*) from public.document_chunks
    where document_id = target_document_id
  ) <> chunk_count then
    raise exception 'Document chunk count does not match ingestion result';
  end if;

  if exists (
    select 1 from public.document_chunks
    where document_id = target_document_id
      and (embedding_status <> 'ready' or embedding is null)
  ) then
    raise exception 'Document contains incomplete embeddings';
  end if;

  update public.documents
  set status = 'ready', updated_at = now()
  where id = target_document_id;

  delete from public.ingestion_jobs
  where id = target_job_id and document_id = target_document_id;

  if not found then
    raise exception 'Ingestion job does not match document';
  end if;
end $$;

revoke all on function public.complete_document_ingestion(uuid,uuid,integer)
from public, anon, authenticated;
grant execute on function public.complete_document_ingestion(uuid,uuid,integer)
to service_role;

-- Remove successful rows left behind by the previous completion function.
delete from public.ingestion_jobs jobs
using public.documents documents
where jobs.document_id = documents.id
  and jobs.status = 'ready'
  and documents.status = 'ready';
