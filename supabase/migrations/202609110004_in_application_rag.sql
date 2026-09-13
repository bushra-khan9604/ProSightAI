-- Move embedding generation into the FastAPI ingestion process while retaining
-- private Storage, RLS, pgvector indexes, and security-invoker hybrid search.

drop trigger if exists queue_chunk_embedding on public.document_chunks;
drop trigger if exists prepare_chunk_embedding on public.document_chunks;
drop trigger if exists update_document_embedding_progress on public.document_chunks;

do $$
declare scheduled_job bigint;
begin
  for scheduled_job in
    select jobid from cron.job where jobname = 'prosight-embedding-worker'
  loop
    perform cron.unschedule(scheduled_job);
  end loop;
end $$;

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

  update public.ingestion_jobs
  set status = 'ready', progress = 100,
      message = format('Indexed %s chunks', greatest(chunk_count, 0)), updated_at = now()
  where id = target_job_id and document_id = target_document_id;

  if not found then
    raise exception 'Ingestion job does not match document';
  end if;
end $$;

revoke all on function public.complete_document_ingestion(uuid,uuid,integer)
from public, anon, authenticated;
grant execute on function public.complete_document_ingestion(uuid,uuid,integer)
to service_role;

drop function if exists public.hybrid_search(
  text, extensions.halfvec, text, integer, date,
  double precision, double precision, integer
);

create or replace function public.hybrid_search(
  query_text text,
  query_embedding extensions.halfvec(1536),
  match_project_code text,
  match_count integer default 8,
  effective_at date default current_date,
  full_text_weight double precision default 1,
  semantic_weight double precision default 1,
  rrf_k integer default 50,
  candidate_count integer default 30
)
returns table (
  id text, document_id uuid, project_code text, filename text,
  page_number integer, content text, content_hash text,
  effective_date date, metadata jsonb, score double precision,
  semantic_similarity double precision, keyword_match boolean
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
with semantic as (
  select
    c.id,
    row_number() over (order by c.embedding <=> query_embedding) as rank,
    (1 - (c.embedding <=> query_embedding))::double precision as similarity
  from public.document_chunks c
  join public.documents d on d.id = c.document_id
  where c.project_code = match_project_code
    and c.effective_date <= effective_at
    and c.embedding_status = 'ready'
    and c.embedding is not null
    and d.status = 'ready'
    and public.has_project_access(c.project_code)
  order by c.embedding <=> query_embedding
  limit least(greatest(candidate_count, 5), 100)
), keyword as (
  select
    c.id,
    row_number() over (
      order by ts_rank_cd(c.fts, websearch_to_tsquery('english', query_text)) desc
    ) as rank
  from public.document_chunks c
  join public.documents d on d.id = c.document_id
  where c.project_code = match_project_code
    and c.effective_date <= effective_at
    and c.embedding_status = 'ready'
    and d.status = 'ready'
    and c.fts @@ websearch_to_tsquery('english', query_text)
    and public.has_project_access(c.project_code)
  order by ts_rank_cd(c.fts, websearch_to_tsquery('english', query_text)) desc
  limit least(greatest(candidate_count, 5), 100)
), fused as (
  select
    coalesce(s.id, k.id) as id,
    coalesce(semantic_weight / (rrf_k + s.rank), 0)
      + coalesce(full_text_weight / (rrf_k + k.rank), 0) as fused_score,
    coalesce(s.similarity, -1)::double precision as semantic_similarity,
    (k.id is not null) as keyword_match
  from semantic s
  full outer join keyword k on s.id = k.id
)
select
  c.id, c.document_id, c.project_code, c.filename, c.page_number,
  c.content, c.content_hash, c.effective_date, c.metadata,
  (f.fused_score + greatest(0, 0.000001 * (c.effective_date - date '2000-01-01')))::double precision,
  f.semantic_similarity, f.keyword_match
from fused f
join public.document_chunks c on c.id = f.id
order by 10 desc
limit least(greatest(match_count, 1), 50)
$$;

revoke all on function public.hybrid_search(
  text,extensions.halfvec,text,integer,date,double precision,double precision,integer,integer
) from public, anon;
grant execute on function public.hybrid_search(
  text,extensions.halfvec,text,integer,date,double precision,double precision,integer,integer
) to authenticated, service_role;

notify pgrst, 'reload schema';
