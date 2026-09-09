"""Admin project erasure across database records and managed source files."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
from .project_locks import project_lock


class ProjectDeletion:
    def __init__(self, repository, rag_store, upload_dir, portfolio_dir):
        self.repository, self.rag_store = repository, rag_store
        self.roots = [Path(upload_dir).resolve(), Path(portfolio_dir).resolve()]

    def delete(self, code, actor_role):
        with project_lock(self.repository, code):
            return self._delete(code, actor_role)

    def _delete(self, code, actor_role):
        if actor_role != 'admin':
            raise PermissionError('Only Admin can delete projects')
        self.repository._ensure()
        # Include JSON previews and historical import rows, with exact code boundaries.
        pattern = re.compile(r'(?<![A-Za-z0-9_-])'+re.escape(code)+r'(?![A-Za-z0-9_-])')
        def mentions(row, identifiers=()):
            return bool(pattern.search(json.dumps(dict(row), default=str))) or any(
                str(row.get(k, '')) in identifiers for k in ('target_id','change_request_id','import_id'))
        tables = ['projects','documents','ingestion_jobs','change_requests','notifications',
                  'audit_events','portfolio_imports','portfolio_import_jobs','manpower_assignments',
                  'project_invoices','project_schedule_activities','employees','employee_training',
                  'attendance_records','payroll_records','direct_allocations','subcontract_crews',
                  'deployment_forecasts','seed_migrations']
        with closing(self.repository.connect()) as db:
            with db:
                if self.repository.backend == 'postgres':
                    db.execute('LOCK TABLE seed_migrations IN EXCLUSIVE MODE')
                    db.execute('LOCK TABLE '+','.join(sorted(t for t in tables if t != 'seed_migrations'))+' IN EXCLUSIVE MODE')
                else:
                    db.execute('BEGIN IMMEDIATE')
                if not db.execute('SELECT code FROM projects WHERE code=?',(code,)).fetchone():
                    raise KeyError('Project not found')
                data = {t:[dict(r) for r in db.execute('SELECT * FROM '+t).fetchall()]
                        for t in tables if t not in {'projects','seed_migrations'}}
                documents = [r for r in data['documents'] if r['project_code']==code]
                doc_ids = {r['id'] for r in documents}
                if any(r['document_id'] in doc_ids and r['status'] in {'queued','processing','indexing'}
                       for r in data['ingestion_jobs']) or any(r['status']=='processing' for r in data['portfolio_imports']):
                    raise ValueError('Wait for active uploads and imports to finish before deleting this project')
                related = {t:[r for r in data[t] if mentions(r)] for t in
                           ['manpower_assignments','project_invoices','project_schedule_activities',
                            'employees','employee_training','attendance_records','payroll_records',
                            'direct_allocations','subcontract_crews','deployment_forecasts',
                            'change_requests','audit_events']}
                normalized_tables = ['manpower_assignments','project_invoices','project_schedule_activities',
                                     'employees','employee_training','attendance_records','payroll_records',
                                     'direct_allocations','subcontract_crews','deployment_forecasts']
                import_ids = {r['import_id'] for t in normalized_tables
                              for r in related[t] if r.get('import_id')}
                for r in related['change_requests']:
                    payload=json.loads(r['payload'])
                    if payload.get('import_id'): import_ids.add(payload['import_id'])
                # Historical imports may only survive in approval/audit records.
                for r in related['audit_events']:
                    for field in ['before_json','after_json']:
                        try: value=json.loads(r.get(field) or '{}')
                        except (ValueError,TypeError): continue
                        if isinstance(value,dict) and value.get('import_id'): import_ids.add(value['import_id'])
                imports=[r for r in data['portfolio_imports'] if r['id'] in import_ids or mentions(r)]
                import_ids.update(r['id'] for r in imports)
                changes=[r for r in data['change_requests'] if mentions(r,import_ids) or
                         any(i in r['payload'] for i in import_ids|doc_ids)]
                identifiers=import_ids|doc_ids|{r['id'] for r in changes}
                jobs=[r for r in data['ingestion_jobs'] if r['document_id'] in doc_ids]
                import_jobs=[r for r in data['portfolio_import_jobs'] if r['import_id'] in import_ids]
                identifiers.update(r['id'] for r in jobs+import_jobs)
                paths={Path(r['stored_path']).resolve() for r in documents+imports if r.get('stored_path')}
                for change in changes:
                    if change['action']=='attachment_update':
                        stored=json.loads(change['payload']).get('stored_path')
                        if stored: paths.add(Path(stored).resolve())
                folder=(self.roots[0]/code).resolve()
                if folder != self.roots[0] and folder.is_relative_to(self.roots[0]) and folder.is_dir():
                    paths.update(p.resolve() for p in folder.rglob('*') if p.is_file())
                for path in paths:
                    if not any(path != root and path.is_relative_to(root) for root in self.roots):
                        raise ValueError('A source file is outside managed upload storage; deletion was stopped')
                if self.repository.backend != 'postgres' and any(d['kind']=='pdf' for d in documents):
                    if not self.rag_store:
                        raise ValueError('RAG storage must be available before deleting PDF evidence')
                    for d in documents:
                        if d['kind']=='pdf': self.rag_store.delete_document(d['id'])
                # Filesystem failures leave database metadata available for a safe retry.
                # Missing files are accepted so interrupted cleanup is idempotent.
                for path in paths: path.unlink(missing_ok=True)
                for table,rows in [('notifications',[r for r in data['notifications'] if mentions(r,identifiers)]),
                                   ('audit_events',[r for r in data['audit_events'] if mentions(r,identifiers)]),
                                   ('ingestion_jobs',jobs),('portfolio_import_jobs',import_jobs),
                                   ('change_requests',changes),('portfolio_imports',imports)]:
                    for row in rows: db.execute('DELETE FROM '+table+' WHERE id=?',(row['id'],))
                for row in related['manpower_assignments']:
                    db.execute('DELETE FROM manpower_assignments WHERE emp_code=?',(row['emp_code'],))
                db.execute('DELETE FROM project_invoices WHERE project_code=?',(code,))
                db.execute('DELETE FROM project_schedule_activities WHERE project_code=?',(code,))
                for table in ['attendance_records','payroll_records','direct_allocations',
                              'subcontract_crews','deployment_forecasts']:
                    db.execute('DELETE FROM '+table+' WHERE project_id=?',(code,))
                # Shared normalized data survives, detached from the removed workbook history.
                for import_id in import_ids:
                    for table in normalized_tables:
                        db.execute('UPDATE '+table+" SET import_id='' WHERE import_id=?",(import_id,))
                db.execute('DELETE FROM documents WHERE project_code=?',(code,))
                db.execute('DELETE FROM projects WHERE code=?',(code,))
                marker='deleted_project:'+hashlib.sha256(code.encode()).hexdigest()
                db.execute('INSERT INTO seed_migrations(migration_key,applied_at) VALUES (?,?) ON CONFLICT DO NOTHING',
                           (marker,self.repository._now()))
        return {'deleted':True,'project_code':code,'documents_deleted':len(documents),'source_files_deleted':len(paths)}
