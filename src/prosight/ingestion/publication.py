"""Approval binding and one-call publication adapter for governed imports."""

from __future__ import annotations

import uuid
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Literal

from .governed_excel import ValidationPreview, checksum


@dataclass(frozen=True)
class ApprovalBinding:
    id: str
    organization_id: str
    batch_id: str
    source_file_id: str
    mapping_profile_id: str
    mapping_version_id: str
    mapping_version_no: int
    source_checksum: str
    profile_checksum: str
    input_profile_checksum: str
    validation_checksum: str
    normalized_preview_checksum: str
    requester_id: str
    approver_id: str
    approver_role: Literal["owner", "admin"]
    decision: Literal["approved", "rejected"]
    transformation_run_id: str | None = None

    def __post_init__(self) -> None:
        for value in (self.id, self.organization_id, self.batch_id, self.source_file_id,
                      self.mapping_profile_id, self.mapping_version_id,
                      self.requester_id, self.approver_id):
            uuid.UUID(value)
        if self.requester_id == self.approver_id:
            raise ValueError("Requester and approver must be distinct")
        if self.transformation_run_id is not None:
            uuid.UUID(self.transformation_run_id)
        if self.approver_role not in {"owner", "admin"}:
            raise PermissionError("Only an organization owner or admin may approve")
        if self.decision not in {"approved", "rejected"}:
            raise ValueError("Approval decision must be approved or rejected")
        if self.mapping_version_no < 1:
            raise ValueError("Mapping versions start at 1")
        for value in (
            self.source_checksum,
            self.profile_checksum,
            self.input_profile_checksum,
            self.validation_checksum,
            self.normalized_preview_checksum,
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError("Approval evidence checksums must be lowercase SHA-256 values")


def bind_approval(
    preview: ValidationPreview, *, approval_id: str, batch_id: str,
    source_file_id: str, mapping_profile_id: str, mapping_version_id: str,
    mapping_version_no: int, requester_id: str,
    approver_id: str, approver_role: Literal["owner", "admin"],
    decision: Literal["approved", "rejected"],
    transformation_run_id: str | None = None,
) -> ApprovalBinding:
    if batch_id != preview.import_batch_id:
        raise ValueError("Approval batch does not match the preview")
    if source_file_id != preview.source_file_id:
        raise ValueError("Approval source file does not match the preview")
    if mapping_profile_id != preview.mapping_profile_id:
        raise ValueError("Approval mapping profile does not match the preview")
    if mapping_version_id != preview.mapping_version_id:
        raise ValueError("Approval mapping does not match the preview")
    if mapping_version_no != preview.mapping_version_no:
        raise ValueError("Approval mapping version does not match the preview")
    if decision == "approved" and not preview.valid:
        raise ValueError("A preview with validation issues cannot be approved")
    return ApprovalBinding(
        id=approval_id,
        organization_id=preview.organization_id,
        batch_id=batch_id,
        source_file_id=source_file_id,
        mapping_profile_id=mapping_profile_id,
        mapping_version_id=mapping_version_id,
        mapping_version_no=mapping_version_no,
        source_checksum=preview.source_checksum,
        profile_checksum=preview.profile_checksum,
        input_profile_checksum=preview.input_profile_checksum,
        validation_checksum=preview.validation_checksum,
        normalized_preview_checksum=preview.normalized_preview_checksum,
        requester_id=requester_id,
        approver_id=approver_id,
        approver_role=approver_role,
        decision=decision,
        transformation_run_id=transformation_run_id,
    )


BATCH_TRANSITIONS = {
    "uploaded": {"profiling", "cancelled"},
    "profiling": {"mapping", "validation_failed", "cancelled"},
    "mapping": {"validating", "validation_failed", "cancelled"},
    "validating": {"review_ready", "validation_failed", "cancelled"},
    "review_ready": {"awaiting_approval", "validating", "cancelled"},
    "awaiting_approval": {"approved", "rejected", "validating", "cancelled"},
    "approved": {"publishing", "cancelled"},
    "publishing": {"published", "publish_failed"},
    "publish_failed": {"approved", "publishing", "cancelled"},
    "validation_failed": {"profiling", "mapping", "validating", "cancelled"},
}


def validate_batch_transition(current: str, requested: str) -> None:
    if requested not in BATCH_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid import batch transition: {current} -> {requested}")


@dataclass(frozen=True)
class PublicationRequest:
    batch_id: str
    approval_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        uuid.UUID(self.batch_id)
        uuid.UUID(self.approval_id)
        if not self.idempotency_key.strip():
            raise ValueError("Publication idempotency key is required")

    @classmethod
    def from_binding(cls, binding: ApprovalBinding) -> "PublicationRequest":
        if binding.decision != "approved":
            raise ValueError("Only an approved binding can be published")
        return cls(
            binding.batch_id,
            binding.id,
            checksum({
                "batch_id": binding.batch_id,
                "approval_id": binding.id,
                "transformation_run_id": binding.transformation_run_id,
                "source_file_id": binding.source_file_id,
                "mapping_profile_id": binding.mapping_profile_id,
                "mapping_version_id": binding.mapping_version_id,
                "mapping_version_no": binding.mapping_version_no,
                "source_checksum": binding.source_checksum,
                "profile_checksum": binding.profile_checksum,
                "input_profile_checksum": binding.input_profile_checksum,
                "validation_checksum": binding.validation_checksum,
                "preview_checksum": binding.normalized_preview_checksum,
            }),
        )


PUBLISH_SQL = """
select *
from ingestion.publish_import_batch(
    %(batch_id)s::uuid,
    %(approval_id)s::uuid,
    %(idempotency_key)s::text
)
"""


class AtomicPublicationAdapter:
    """Invoke the controlled database publisher exactly once.

    The database routine owns authorization rechecks, advisory locking,
    operational upserts, lineage writes, and transaction atomicity.  The
    application intentionally cannot issue per-row operational writes.
    """

    def __init__(self, connection_factory):
        self.connection_factory = connection_factory

    def publish(self, request: PublicationRequest) -> dict[str, Any]:
        params = {
            "batch_id": request.batch_id,
            "approval_id": request.approval_id,
            "idempotency_key": request.idempotency_key,
        }
        with closing(self.connection_factory()) as connection:
            with connection:
                row = connection.execute_native(PUBLISH_SQL, params).fetchone()
        if row is None:
            raise RuntimeError("Publication routine returned no result")
        result = dict(row)
        if result.get("status") not in {"published", "already_published"}:
            raise RuntimeError("Publication did not reach an idempotent terminal state")
        return result
