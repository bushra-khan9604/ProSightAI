-- ProSight AI: PostgreSQL, Auth/RLS, Storage, pgvector, and embedding queue.
create extension if not exists pgcrypto with schema extensions;
create extension if not exists vector with schema extensions;
create extension if not exists pgmq;
create extension if not exists pg_net with schema extensions;
create extension if not exists pg_cron;
create extension if not exists supabase_vault with schema vault;

do $$ begin
  create type public.app_role as enum ('employee', 'project_manager', 'planning_engineer', 'admin');
exception when duplicate_object then null;
end $$;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  display_name text not null default '',
  role public.app_role not null default 'employee',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.projects (
  code text primary key,
  name text not null,
  status text not null check (status in ('completed', 'active', 'future')),
  client text not null,
  location text not null,
  contract_value_usd numeric(18,2) not null default 0,
  planned_start date not null,
  planned_finish date not null,
  revised_finish date,
  reporting_date date not null,
  baseline_progress numeric(6,2) not null default 0,
  revised_progress numeric(6,2) not null default 0,
  actual_progress numeric(6,2) not null default 0,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.project_memberships (
  user_id uuid not null references public.profiles(id) on delete cascade,
  project_code text not null references public.projects(code) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, project_code)
);

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  project_code text not null references public.projects(code) on delete cascade,
  uploaded_by uuid references public.profiles(id) on delete set null,
  filename text not null,
  kind text not null check (kind in ('pdf', 'xlsx')),
  checksum text not null,
  storage_bucket text not null default 'project-documents',
  storage_key text not null,
  status text not null default 'queued',
  reporting_date date,
  effective_date date,
  date_status text not null default 'pending',
  revision text,
  document_type text,
  security_classification text not null default 'internal',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(project_code, checksum)
);

create table if not exists public.ingestion_jobs (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  status text not null default 'queued',
  progress integer not null default 0 check (progress between 0 and 100),
  message text,
  change_request_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.document_chunks (
  id text primary key,
  document_id uuid not null references public.documents(id) on delete cascade,
  project_code text not null references public.projects(code) on delete cascade,
  filename text not null,
  page_number integer not null check (page_number > 0),
  chunk_number integer not null check (chunk_number > 0),
  content text not null,
  content_hash text not null,
  token_count integer not null default 0,
  reporting_date date,
  effective_date date not null default current_date,
  date_status text not null default 'fallback',
  metadata jsonb not null default '{}'::jsonb,
  fts tsvector generated always as (to_tsvector('english', content)) stored,
  embedding extensions.halfvec(1536),
  embedding_model text not null default 'text-embedding-3-small',
  embedding_version integer not null default 1,
  embedding_status text not null default 'pending' check (embedding_status in ('pending','processing','ready','failed')),
  embedding_error text,
  embedding_attempts integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(document_id, page_number, chunk_number)
);

create index if not exists document_chunks_fts_idx on public.document_chunks using gin(fts);
create index if not exists document_chunks_embedding_idx
  on public.document_chunks using hnsw (embedding extensions.halfvec_cosine_ops)
  where embedding is not null;
create index if not exists document_chunks_project_effective_idx
  on public.document_chunks(project_code, effective_date desc);

create table if not exists public.change_requests (
  id uuid primary key default gen_random_uuid(),
  action text not null,
  project_code text not null,
  payload jsonb not null,
  preview jsonb not null,
  status text not null default 'pending',
  requested_by uuid not null references public.profiles(id),
  decided_by uuid references public.profiles(id),
  requested_role public.app_role not null,
  decided_role public.app_role,
  created_at timestamptz not null default now(),
  decided_at timestamptz
);
alter table public.ingestion_jobs drop constraint if exists ingestion_jobs_change_request_id_fkey;
alter table public.ingestion_jobs add constraint ingestion_jobs_change_request_id_fkey
  foreign key (change_request_id) references public.change_requests(id) on delete set null;

create table if not exists public.audit_events (
  id uuid primary key default gen_random_uuid(),
  request_id text,
  actor_user_id uuid references public.profiles(id) on delete set null,
  actor_role public.app_role not null,
  action text not null,
  target_type text not null,
  target_id text not null,
  before_json jsonb,
  after_json jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  recipient_user_id uuid not null references public.profiles(id) on delete cascade,
  event_type text not null,
  project_code text not null,
  change_request_id uuid,
  title text not null,
  message text not null,
  read_at timestamptz,
  created_at timestamptz not null default now(),
  unique(recipient_user_id, event_type, change_request_id)
);
create index if not exists notifications_user_created_idx
  on public.notifications(recipient_user_id, created_at desc);

create table if not exists public.portfolio_imports (
  id uuid primary key default gen_random_uuid(),
  filename text not null,
  checksum text not null,
  storage_bucket text not null default 'portfolio-imports',
  storage_key text not null,
  uploaded_by uuid not null references public.profiles(id),
  dataset text,
  project_code text references public.projects(code),
  status text not null,
  summary_json jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists public.portfolio_import_jobs (
  id uuid primary key default gen_random_uuid(),
  import_id uuid not null unique references public.portfolio_imports(id) on delete cascade,
  status text not null,
  progress integer not null default 0,
  message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.manpower_assignments (
  emp_code text primary key,
  current_project_code text not null references public.projects(code),
  mobilized_project_code text,
  name text not null,
  designation text,
  department text,
  category text,
  current_location text,
  allocation text,
  status text,
  leave_balance numeric,
  data_json jsonb not null,
  updated_at timestamptz not null default now(),
  import_id uuid references public.portfolio_imports(id)
);

create table if not exists public.project_invoices (
  job_number text not null,
  draft_invoice_number text not null,
  project_code text not null references public.projects(code),
  levels text,
  status text,
  approval_status text,
  payment_status text,
  risk_profile text,
  invoice_value_usd numeric(18,2) not null,
  invoice_value_aed numeric(18,2),
  submission_date date,
  expected_remittance_date date,
  data_json jsonb not null,
  updated_at timestamptz not null default now(),
  import_id uuid references public.portfolio_imports(id),
  primary key(job_number, draft_invoice_number)
);

create table if not exists public.project_schedule_activities (
  project_code text not null references public.projects(code) on delete cascade,
  activity_id text not null,
  activity_name text not null,
  start_date date not null,
  finish_date date not null,
  original_duration integer not null,
  import_id uuid references public.portfolio_imports(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key(project_code, activity_id)
);

create or replace function public.current_app_role()
returns public.app_role language sql stable security definer set search_path = public
as $$ select role from public.profiles where id = auth.uid() $$;

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public
as $$ select coalesce(public.current_app_role() = 'admin', false) $$;

create or replace function public.has_project_access(code text)
returns boolean language sql stable security definer set search_path = public
as $$
  select public.is_admin() or exists (
    select 1 from public.project_memberships
    where user_id = auth.uid() and project_code = code
  )
$$;

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
  insert into public.profiles(id, email, display_name, role)
  values (new.id, coalesce(new.email, ''), coalesce(new.raw_user_meta_data->>'display_name', ''), 'employee')
  on conflict (id) do nothing;
  insert into public.project_memberships(user_id, project_code)
  select new.id, code from public.projects on conflict do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
for each row execute function public.handle_new_user();

create or replace function public.grant_new_project_access()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
  insert into public.project_memberships(user_id, project_code)
  select id, new.code from public.profiles where role = 'employee' on conflict do nothing;
  if auth.uid() is not null then
    insert into public.project_memberships(user_id, project_code)
    values(auth.uid(), new.code) on conflict do nothing;
  end if;
  return new;
end $$;

drop trigger if exists on_project_created on public.projects;
create trigger on_project_created after insert on public.projects
for each row execute function public.grant_new_project_access();

create or replace function public.prepare_chunk_embedding()
returns trigger language plpgsql set search_path = public, extensions
as $$
begin
  new.content_hash := encode(digest(new.content, 'sha256'), 'hex');
  if tg_op = 'INSERT' or new.content is distinct from old.content or new.embedding_model is distinct from old.embedding_model then
    new.embedding := null;
    new.embedding_status := 'pending';
    new.embedding_error := null;
    new.embedding_attempts := 0;
  end if;
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists prepare_chunk_embedding on public.document_chunks;
create trigger prepare_chunk_embedding before insert or update of content, embedding_model
on public.document_chunks for each row execute function public.prepare_chunk_embedding();

select pgmq.create('prosight_embedding_jobs')
where not exists (select 1 from pgmq.list_queues() where queue_name = 'prosight_embedding_jobs');

create or replace function public.queue_chunk_embedding()
returns trigger language plpgsql security definer set search_path = public, pgmq
as $$
begin
  perform pgmq.send('prosight_embedding_jobs', jsonb_build_object(
    'chunk_id', new.id, 'content_hash', new.content_hash, 'embedding_model', new.embedding_model
  ));
  return new;
end $$;

drop trigger if exists queue_chunk_embedding on public.document_chunks;
create trigger queue_chunk_embedding after insert or update of content_hash, embedding_model
on public.document_chunks for each row
when (new.embedding_status = 'pending') execute function public.queue_chunk_embedding();

create or replace function public.dequeue_embedding_jobs(batch_size integer default 16)
returns table(msg_id bigint, message jsonb)
language sql security definer set search_path = public, pgmq
as $$ select msg_id, message from pgmq.read('prosight_embedding_jobs', 120, least(greatest(batch_size,1),64)) $$;

create or replace function public.complete_embedding_job(job_msg_id bigint)
returns void language sql security definer set search_path = public, pgmq
as $$ select pgmq.delete('prosight_embedding_jobs', job_msg_id) $$;

create or replace function public.retry_embedding_job(job_msg_id bigint, job_message jsonb, delay_seconds integer default 60)
returns void language plpgsql security definer set search_path = public, pgmq
as $$
begin
  perform pgmq.delete('prosight_embedding_jobs', job_msg_id);
  perform pgmq.send('prosight_embedding_jobs', job_message, greatest(delay_seconds, 1));
end $$;

revoke all on function public.dequeue_embedding_jobs(integer) from public, anon, authenticated;
revoke all on function public.complete_embedding_job(bigint) from public, anon, authenticated;
revoke all on function public.retry_embedding_job(bigint,jsonb,integer) from public, anon, authenticated;
grant execute on function public.dequeue_embedding_jobs(integer) to service_role;
grant execute on function public.complete_embedding_job(bigint) to service_role;
grant execute on function public.retry_embedding_job(bigint,jsonb,integer) to service_role;

create or replace function public.update_document_embedding_progress()
returns trigger language plpgsql security definer set search_path = public
as $$
declare total_count integer; ready_count integer; failed_count integer;
begin
  select count(*), count(*) filter(where embedding_status='ready'), count(*) filter(where embedding_status='failed')
  into total_count, ready_count, failed_count from public.document_chunks where document_id = new.document_id;
  update public.documents set
    status = case when failed_count > 0 then 'failed' when total_count > 0 and ready_count = total_count then 'ready' else 'embedding' end,
    updated_at = now()
  where id = new.document_id;
  update public.ingestion_jobs set
    status = case when failed_count > 0 then 'failed' when total_count > 0 and ready_count = total_count then 'ready' else 'embedding' end,
    progress = case when total_count = 0 then 0 else least(100, 40 + round(60.0 * ready_count / total_count)::integer) end,
    message = case when failed_count > 0 then 'Embedding failed' when ready_count = total_count then 'Document ready' else 'Generating embeddings' end,
    updated_at = now()
  where document_id = new.document_id;
  return new;
end $$;

drop trigger if exists update_document_embedding_progress on public.document_chunks;
create trigger update_document_embedding_progress after update of embedding_status
on public.document_chunks for each row execute function public.update_document_embedding_progress();

create or replace function public.hybrid_search(
  query_text text,
  query_embedding extensions.halfvec(1536),
  match_project_code text,
  match_count integer default 5,
  effective_at date default current_date,
  full_text_weight double precision default 1,
  semantic_weight double precision default 1,
  rrf_k integer default 50
)
returns table (
  id text, document_id uuid, project_code text, filename text,
  page_number integer, content text, effective_date date, metadata jsonb, score double precision
)
language sql stable security invoker set search_path = public, extensions
as $$
with semantic as (
  select c.id, row_number() over(order by c.embedding <=> query_embedding) as rank
  from public.document_chunks c join public.documents d on d.id=c.document_id
  where c.project_code=match_project_code and c.effective_date <= effective_at
    and c.embedding_status='ready' and d.status='ready'
    and public.has_project_access(c.project_code)
  order by c.embedding <=> query_embedding limit least(match_count * 4, 40)
), keyword as (
  select c.id, row_number() over(order by ts_rank_cd(c.fts, websearch_to_tsquery('english', query_text)) desc) as rank
  from public.document_chunks c join public.documents d on d.id=c.document_id
  where c.project_code=match_project_code and c.effective_date <= effective_at
    and c.embedding_status='ready' and d.status='ready'
    and c.fts @@ websearch_to_tsquery('english', query_text) and public.has_project_access(c.project_code)
  order by ts_rank_cd(c.fts, websearch_to_tsquery('english', query_text)) desc limit least(match_count * 4, 40)
), fused as (
  select coalesce(s.id,k.id) id,
    coalesce(semantic_weight/(rrf_k+s.rank),0) + coalesce(full_text_weight/(rrf_k+k.rank),0) fused_score
  from semantic s full outer join keyword k on s.id=k.id
)
select c.id,c.document_id,c.project_code,c.filename,c.page_number,c.content,c.effective_date,c.metadata,
  (f.fused_score + greatest(0, 0.000001 * (c.effective_date - date '2000-01-01')))::double precision score
from fused f join public.document_chunks c on c.id=f.id
order by score desc limit least(match_count,20)
$$;

-- Row-level security. FastAPI forwards the caller JWT to the Data API.
alter table public.profiles enable row level security;
alter table public.project_memberships enable row level security;
alter table public.projects enable row level security;
alter table public.documents enable row level security;
alter table public.ingestion_jobs enable row level security;
alter table public.document_chunks enable row level security;
alter table public.change_requests enable row level security;
alter table public.audit_events enable row level security;
alter table public.notifications enable row level security;
alter table public.portfolio_imports enable row level security;
alter table public.portfolio_import_jobs enable row level security;
alter table public.manpower_assignments enable row level security;
alter table public.project_invoices enable row level security;
alter table public.project_schedule_activities enable row level security;

create policy "profiles_read_self_or_admin" on public.profiles for select to authenticated
using (id=auth.uid() or public.is_admin());
create policy "profiles_admin_update" on public.profiles for update to authenticated
using (public.is_admin()) with check (public.is_admin());
create policy "memberships_read_self_or_admin" on public.project_memberships for select to authenticated
using (user_id=auth.uid() or public.is_admin());
create policy "memberships_admin_write" on public.project_memberships for all to authenticated
using (public.is_admin()) with check (public.is_admin());
create policy "projects_member_read" on public.projects for select to authenticated
using (public.has_project_access(code));
create policy "projects_author_write" on public.projects for all to authenticated
using (public.has_project_access(code) and public.current_app_role() in ('project_manager','planning_engineer','admin'))
with check (public.current_app_role() in ('project_manager','planning_engineer','admin'));
create policy "documents_member_read" on public.documents for select to authenticated using (public.has_project_access(project_code));
create policy "documents_author_write" on public.documents for all to authenticated
using (public.has_project_access(project_code) and public.current_app_role() in ('project_manager','planning_engineer','admin'))
with check (public.has_project_access(project_code) and public.current_app_role() in ('project_manager','planning_engineer','admin'));
create policy "jobs_member_access" on public.ingestion_jobs for select to authenticated
using (exists(select 1 from public.documents d where d.id=document_id and public.has_project_access(d.project_code)));
create policy "chunks_member_read" on public.document_chunks for select to authenticated using (public.has_project_access(project_code));
create policy "changes_member_read" on public.change_requests for select to authenticated
using (public.has_project_access(project_code) or requested_by=auth.uid());
create policy "changes_author_insert" on public.change_requests for insert to authenticated
with check (requested_by=auth.uid() and public.has_project_access(project_code) and public.current_app_role() in ('project_manager','admin'));
create policy "changes_admin_update" on public.change_requests for update to authenticated using (public.is_admin()) with check(public.is_admin());
create policy "audits_admin_read" on public.audit_events for select to authenticated using(public.is_admin());
create policy "notifications_owner_access" on public.notifications for select to authenticated using(recipient_user_id=auth.uid());
create policy "notifications_owner_update" on public.notifications for update to authenticated using(recipient_user_id=auth.uid()) with check(recipient_user_id=auth.uid());
create policy "imports_member_read" on public.portfolio_imports for select to authenticated
using (project_code is null or public.has_project_access(project_code));
create policy "import_jobs_member_read" on public.portfolio_import_jobs for select to authenticated
using (exists(select 1 from public.portfolio_imports i where i.id=import_id and (i.project_code is null or public.has_project_access(i.project_code))));
create policy "manpower_member_read" on public.manpower_assignments for select to authenticated using(public.has_project_access(current_project_code));
create policy "invoices_member_read" on public.project_invoices for select to authenticated using(public.has_project_access(project_code));
create policy "schedule_member_read" on public.project_schedule_activities for select to authenticated using(public.has_project_access(project_code));

insert into storage.buckets(id,name,public) values
  ('project-documents','project-documents',false),('portfolio-imports','portfolio-imports',false)
on conflict(id) do update set public=false;

create policy "project_files_member_read" on storage.objects for select to authenticated
using (bucket_id='project-documents' and public.has_project_access((storage.foldername(name))[1]));
create policy "project_files_author_insert" on storage.objects for insert to authenticated
with check (bucket_id='project-documents' and public.has_project_access((storage.foldername(name))[1])
  and public.current_app_role() in ('project_manager','planning_engineer','admin'));
create policy "project_files_admin_delete" on storage.objects for delete to authenticated
using (bucket_id='project-documents' and public.is_admin());
create policy "portfolio_files_authenticated" on storage.objects for select to authenticated
using (bucket_id='portfolio-imports');
create policy "portfolio_files_author_insert" on storage.objects for insert to authenticated
with check (bucket_id='portfolio-imports' and public.current_app_role() in ('project_manager','planning_engineer','admin'));
