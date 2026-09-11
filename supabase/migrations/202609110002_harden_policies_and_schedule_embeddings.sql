-- Tighten mutation policies and schedule the private embedding worker.
drop policy if exists "projects_author_write" on public.projects;
create policy "projects_author_update" on public.projects for update to authenticated
using (
  public.has_project_access(code)
  and public.current_app_role() in ('project_manager','planning_engineer','admin')
)
with check (
  public.has_project_access(code)
  and public.current_app_role() in ('project_manager','planning_engineer','admin')
);

drop policy if exists "documents_author_write" on public.documents;
create policy "documents_author_insert" on public.documents for insert to authenticated
with check (
  uploaded_by = auth.uid()
  and public.has_project_access(project_code)
  and public.current_app_role() in ('project_manager','planning_engineer','admin')
);
create policy "documents_author_update" on public.documents for update to authenticated
using (
  public.has_project_access(project_code)
  and public.current_app_role() in ('project_manager','planning_engineer','admin')
)
with check (
  public.has_project_access(project_code)
  and public.current_app_role() in ('project_manager','planning_engineer','admin')
);
create policy "documents_admin_delete" on public.documents for delete to authenticated
using (public.is_admin());

drop policy if exists "changes_author_insert" on public.change_requests;
create policy "changes_author_insert" on public.change_requests for insert to authenticated
with check (
  requested_by = auth.uid()
  and public.current_app_role() in ('project_manager','planning_engineer','admin')
  and (
    public.has_project_access(project_code)
    or (
      action = 'excel_import'
      and not exists (select 1 from public.projects p where p.code = project_code)
    )
  )
);
create policy "changes_requester_edit_pending" on public.change_requests for update to authenticated
using (
  requested_by = auth.uid()
  and status = 'pending'
  and public.current_app_role() in ('project_manager','admin')
)
with check (
  requested_by = auth.uid()
  and status = 'pending'
  and public.current_app_role() in ('project_manager','admin')
);

drop policy if exists "imports_member_read" on public.portfolio_imports;
create policy "imports_owner_or_admin_read" on public.portfolio_imports for select to authenticated
using (uploaded_by = auth.uid() or public.is_admin());
drop policy if exists "import_jobs_member_read" on public.portfolio_import_jobs;
create policy "import_jobs_owner_or_admin_read" on public.portfolio_import_jobs for select to authenticated
using (
  exists (
    select 1 from public.portfolio_imports i
    where i.id = import_id and (i.uploaded_by = auth.uid() or public.is_admin())
  )
);

drop policy if exists "portfolio_files_authenticated" on storage.objects;
create policy "portfolio_files_owner_or_admin_read" on storage.objects for select to authenticated
using (
  bucket_id = 'portfolio-imports'
  and ((storage.foldername(name))[1] = auth.uid()::text or public.is_admin())
);

revoke all on function public.dequeue_embedding_jobs(integer) from public, anon, authenticated;
revoke all on function public.complete_embedding_job(bigint) from public, anon, authenticated;
revoke all on function public.retry_embedding_job(bigint,jsonb,integer) from public, anon, authenticated;
grant execute on function public.dequeue_embedding_jobs(integer) to service_role;
grant execute on function public.complete_embedding_job(bigint) to service_role;
grant execute on function public.retry_embedding_job(bigint,jsonb,integer) to service_role;

revoke all on function public.hybrid_search(text,extensions.halfvec,text,integer,date,double precision,double precision,integer) from public, anon;
grant execute on function public.hybrid_search(text,extensions.halfvec,text,integer,date,double precision,double precision,integer)
to authenticated, service_role;

-- Create these Vault secrets before rollout:
--   prosight_embedding_worker_url
--   prosight_embedding_worker_secret
-- The cron statement resolves them at execution time, so no secret enters git.
select cron.unschedule(jobid) from cron.job where jobname = 'prosight-embedding-worker';
select cron.schedule(
  'prosight-embedding-worker',
  '* * * * *',
  $job$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets
            where name = 'prosight_embedding_worker_url' limit 1),
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-worker-secret', (select decrypted_secret from vault.decrypted_secrets
                          where name = 'prosight_embedding_worker_secret' limit 1)
    ),
    body := '{"batch_size":16}'::jsonb
  );
  $job$
);
