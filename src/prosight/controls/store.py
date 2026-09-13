"""RLS-bound controls persistence. Mutations use transactional database functions."""
from __future__ import annotations

import hashlib
import json

from .workbooks import merge_files, validate


class ControlsStore:
    def __init__(self, repository):
        self.repository = repository
        self.db = repository.user

    def active(self, code):
        rows = self.db.select("controls_versions", project_code=f"eq.{code}", status="eq.active", limit="1")
        return rows[0] if rows else None

    def version(self, code, version_id):
        rows = self.db.select("controls_versions", project_code=f"eq.{code}", id=f"eq.{version_id}", limit="1")
        if not rows:
            raise KeyError("Controls version not found or unauthorized")
        return rows[0]

    def stage(self, code, parsed_files, *, parent_id=None, tables=None, reporting_date=None):
        project = self.repository.find_project(code)
        if not project:
            raise KeyError("Project not found or unauthorized")
        parent = self.version(code, parent_id) if parent_id else self.active(code)
        data = tables if tables is not None else merge_files(parsed_files, parent["content"] if parent else None)
        # An unchanged reupload resolves to the same immutable version, including after activation.
        if parent and data == parent['content']:
            return parent
        overview = (data.get("Overview") or [{}])[0]
        master = (data.get("Project Master") or [project])[0]
        cutoff = reporting_date or overview.get("data_date") or master.get("reporting_date") or project["reporting_date"]
        report = validate(data, project, cutoff)
        report['before_counts']={k:len(v) for k,v in (parent['content'] if parent else {}).items()}
        metadata = {"reporting_date": cutoff, "construction_cutoff": overview.get("construction_finish"),
                    "financial_cutoff": overview.get("financial_asof") or cutoff,
                    "synthetic": any(f.get("metadata", {}).get("synthetic") for f in parsed_files) or bool(parent and parent.get("synthetic")),
                    "source_files": (parent.get('source_files',[]) if parent else []) + [{k: f[k] for k in ("filename", "checksum", "sources") if k in f} for f in parsed_files]}
        digest = hashlib.sha256(json.dumps({"content": data, "metadata": metadata, "parent": parent["id"] if parent else None}, sort_keys=True, default=str).encode()).hexdigest()
        return self.db.rpc("stage_controls_version", {"p_code": code, "p_parent": parent["id"] if parent else None,
                           "p_content": data, "p_metadata": metadata, "p_validation": report, "p_checksum": digest})

    def submit(self, code, version_id):
        version = self.version(code, version_id)
        if version['status']=='active':
            return {'status':'already_active','version_id':version_id}
        project = self.repository.find_project(code)
        validate(version["content"], project, version["reporting_date"])
        return self.db.rpc("submit_controls_version", {"p_id": version_id})

    def decide(self, change_id, approved):
        if approved:
            change=self.repository.get_change_request(change_id)
            if not change:raise KeyError('Change request not found')
            version=self.version(change['project_code'],change['payload']['version_id'])
            validate(version['content'],self.repository.find_project(change['project_code']),version['reporting_date'])
        return self.db.rpc("decide_controls_version", {"p_change": change_id, "p_approve": approved})
