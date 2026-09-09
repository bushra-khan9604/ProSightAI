"""Validated project records shared by API and attachment tools."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class ProjectDraft(BaseModel):
    """Validated new-project payload stored as an approval request."""

    model_config=ConfigDict(allow_inf_nan=False,json_schema_extra={'allOf':[{
        'if':{'properties':{'status':{'const':'active'}},'required':['status']},
        'then':{'required':['actual_progress','reporting_date'],'properties':{'actual_progress':{'type':'number'},'reporting_date':{'type':'string'}}}
    }]})

    code: str = Field(pattern=r"^[A-Z0-9-]{3,30}$")
    name: str = Field(min_length=3, max_length=200)
    status: Literal["active", "completed", "future"]
    client: str = Field(min_length=2, max_length=200)
    location: str = Field(min_length=2, max_length=200)
    contract_value_usd: float = Field(ge=0)
    planned_start: str
    planned_finish: str
    revised_finish: str | None = None
    reporting_date: str | None = None
    baseline_progress: float | None = Field(default=None,ge=0, le=100)
    revised_progress: float | None = Field(default=None,ge=0, le=100)
    actual_progress: float | None = Field(default=None,ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def normalize_status(cls,value):
        if isinstance(value,dict) and value.get('status') in {'future','completed'}:
            value=dict(value)
            for field in ('baseline_progress','revised_progress','actual_progress','reporting_date','revised_finish'):value[field]=None
        return value

    @model_validator(mode="after")
    def status_requirements(self):
        if self.status=='active' and (self.actual_progress is None or self.reporting_date is None):
            raise ValueError('Active projects require completed progress and a reporting date')
        return self

    def storage_record(self):
        """Keep legacy NOT NULL columns compatible while recording unavailable metrics."""
        data=self.model_dump()
        data['progress_fields_provided']=[field for field in ('baseline_progress','revised_progress','actual_progress') if data[field] is not None and self.status=='active']
        for field in ('baseline_progress','revised_progress','actual_progress'):
            data[field]=(data[field] if data[field] is not None else 0) if self.status=='active' else (100 if self.status=='completed' else 0)
        data['reporting_date_provided']=self.reporting_date is not None
        data['reporting_date']=self.reporting_date or (self.planned_finish if self.status=='completed' else self.planned_start)
        return data

    @model_validator(mode="after")
    def validate_dates(self) -> "ProjectDraft":
        """Require ISO dates and coherent project schedule boundaries."""
        try:
            planned_start = date.fromisoformat(self.planned_start)
            planned_finish = date.fromisoformat(self.planned_finish)
            revised_finish = date.fromisoformat(self.revised_finish) if self.revised_finish else None
            if self.reporting_date:date.fromisoformat(self.reporting_date)
        except ValueError as error:
            raise ValueError("Project dates must use YYYY-MM-DD format") from error
        if planned_finish < planned_start:
            raise ValueError("Planned finish cannot be before planned start")
        if revised_finish and revised_finish < planned_start:
            raise ValueError("Revised finish cannot be before planned start")
        return self


class ProjectUpdate(BaseModel):
    """Validated mutable fields for an existing project."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=200)
    status: Literal["active", "completed", "future"]
    client: str = Field(min_length=2, max_length=200)
    location: str = Field(min_length=2, max_length=200)
    contract_value_usd: float = Field(ge=0)
    planned_start: str
    planned_finish: str
    revised_finish: str | None = None
    reporting_date: str | None = None
    baseline_progress: float | None = Field(default=None,ge=0, le=100)
    revised_progress: float | None = Field(default=None,ge=0, le=100)
    actual_progress: float | None = Field(default=None,ge=0, le=100)

    @model_validator(mode="after")
    def validate_dates(self) -> "ProjectUpdate":
        """Apply the same date invariants as new-project creation."""
        ProjectDraft(code="VALIDATION", **self.model_dump())
        return self


    def storage_record(self):
        data=ProjectDraft(code='VALIDATION',**self.model_dump()).storage_record()
        data.pop('code')
        return data
