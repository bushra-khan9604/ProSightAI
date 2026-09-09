"""Administrator-controlled workbook mappings; never sourced from uploaded cells."""
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    aliases: list[str] = Field(default_factory=list)
    column: int | None = Field(default=None, ge=1, le=16384)


class SheetMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    aliases: list[str] = Field(min_length=1)
    header_row: int | None = Field(default=None, ge=1, le=1048576)
    data_start_row: int | None = Field(default=None, ge=1, le=1048576)
    fields: dict[str, FieldMapping]


class WorkforceMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: int = Field(ge=1, le=1)
    profile_id: str = Field(min_length=1)
    sheets: dict[str, SheetMapping]


def load_workforce_mapping(specs):
    path = Path(os.environ.get('PROSIGHT_WORKFORCE_MAPPING_PATH') or
                Path(__file__).parents[1] / 'schemas' / 'workforce-mapping.json')
    try:
        profile = WorkforceMapping.model_validate(json.loads(path.read_text(encoding='utf-8')))
        if set(profile.sheets) != set(specs):
            raise ValueError('Profile must define each supported worksheet type')
        for name, rule in profile.sheets.items():
            if set(rule.fields) != set(specs[name].fields.values()):
                raise ValueError(f'{name}: profile fields must match the record schema')
            columns = [field.column for field in rule.fields.values() if field.column is not None]
            if len(columns) != len(set(columns)):
                raise ValueError(f'{name}: two fields cannot use the same column')
            if rule.header_row and rule.data_start_row and rule.data_start_row <= rule.header_row:
                raise ValueError(f'{name}: data must start after the header')
        return profile
    except (OSError, ValueError) as error:
        raise ValueError(f'Invalid workforce mapping profile: {error}') from error
