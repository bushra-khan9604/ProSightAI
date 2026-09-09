"""Validated schemas for governed workforce and deployment imports."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


Identifier = Annotated[
    str,
    Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"),
]
Label = Annotated[str, Field(min_length=1, max_length=200)]
NonNegative = Annotated[float, Field(ge=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class WorkforceRecord(BaseModel):
    """Strict base model shared by records that may reach the database."""

    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, str_strip_whitespace=True
    )


class EmployeeRecord(WorkforceRecord):
    employee_id: Identifier
    synthetic_name: Label
    role: Label
    department: Label
    home_project_id: Identifier
    employment_type: Label
    join_date: date
    basic_aed: NonNegative
    allowance_aed: NonNegative
    gross_monthly_aed: NonNegative
    status: Label
    data_origin: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def gross_matches_components(self):
        expected = self.basic_aed + self.allowance_aed
        if abs(self.gross_monthly_aed - expected) > 0.01:
            raise ValueError("Gross monthly AED must equal basic AED plus allowance AED")
        return self


class TrainingRecord(WorkforceRecord):
    training_id: Identifier
    employee_id: Identifier
    course: Label
    completed_date: date
    expiry_date: date | None = None
    status: Label
    evidence_id: Identifier | None = None

    @model_validator(mode="after")
    def expiry_follows_completion(self):
        if self.expiry_date and self.expiry_date < self.completed_date:
            raise ValueError("Training expiry date cannot be before completed date")
        return self


class AttendanceRecord(WorkforceRecord):
    timesheet_id: Identifier
    employee_id: Identifier
    project_id: Identifier
    work_date: date
    attendance_status: Label
    regular_hours: Annotated[float, Field(ge=0, le=24)]
    ot_hours: Annotated[float, Field(ge=0, le=24)]
    total_hours: Annotated[float, Field(ge=0, le=24)]

    @model_validator(mode="after")
    def total_matches_hours(self):
        if abs(self.total_hours - self.regular_hours - self.ot_hours) > 0.01:
            raise ValueError("Total hours must equal regular hours plus OT hours")
        return self


class PayrollRecord(WorkforceRecord):
    payroll_id: Identifier
    employee_id: Identifier
    project_id: Identifier
    month: date
    basic_aed: NonNegative
    allowance_aed: NonNegative
    ot_hours: NonNegative
    ot_rate_aed: NonNegative
    ot_pay_aed: NonNegative
    gross_aed: NonNegative
    employer_burden_aed: NonNegative
    total_cost_aed: NonNegative
    payment_date: date
    days_worked: Annotated[int, Field(ge=0, le=31)]
    paid_leave_days: Annotated[int, Field(ge=0, le=31)]

    @model_validator(mode="after")
    def calculated_pay_matches_components(self):
        expected_ot = self.ot_hours * self.ot_rate_aed
        expected_gross = self.basic_aed + self.allowance_aed
        expected_total = expected_ot + expected_gross + self.employer_burden_aed
        if abs(self.ot_pay_aed - expected_ot) > 0.01:
            raise ValueError("OT pay AED must equal OT hours multiplied by OT rate AED")
        if abs(self.gross_aed - expected_gross) > 0.01:
            raise ValueError("Gross AED must equal basic AED plus allowance AED")
        if abs(self.total_cost_aed - expected_total) > 0.01:
            raise ValueError("Total cost AED must equal OT pay, gross, and employer burden")
        return self


class DirectAllocationRecord(WorkforceRecord):
    employee_id: Identifier
    project_id: Identifier
    month: date
    fte_allocation: Annotated[float, Field(ge=0, le=1)]
    regular_hours: NonNegative
    ot_hours: NonNegative
    payroll_cost_aed: NonNegative
    basis: str | None = Field(default=None, max_length=500)


class SubcontractCrewRecord(WorkforceRecord):
    subcontract_id: Identifier
    project_id: Identifier
    vendor_id: Identifier
    month: date
    trade: Label
    planned_workers: NonNegativeInt
    actual_workers: NonNegativeInt
    worker_variance: int
    available_labor_hours: NonNegative
    definition: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def calculated_capacity_matches_workers(self):
        if self.worker_variance != self.actual_workers - self.planned_workers:
            raise ValueError("Worker variance must equal actual workers minus planned workers")
        if abs(self.available_labor_hours - self.actual_workers * 208) > 0.01:
            raise ValueError("Available labor hours must equal actual workers multiplied by 208")
        return self


class DeploymentForecastRecord(WorkforceRecord):
    project_id: Identifier
    month: date
    direct_headcount: NonNegativeInt
    subcontract_workers: NonNegativeInt
    basis: str | None = Field(default=None, max_length=500)


WORKFORCE_SCHEMAS = {
    "employees": EmployeeRecord,
    "training": TrainingRecord,
    "attendance": AttendanceRecord,
    "payroll": PayrollRecord,
    "direct_allocations": DirectAllocationRecord,
    "subcontract_crews": SubcontractCrewRecord,
    "deployment_forecasts": DeploymentForecastRecord,
}


def workforce_schema_catalog() -> dict[str, dict]:
    """Return JSON Schema documents for API clients and mapping review."""
    return {name: model.model_json_schema() for name, model in WORKFORCE_SCHEMAS.items()}
