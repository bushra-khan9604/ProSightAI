"""Validated organization mapping configuration; contains data, never executable code."""
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..config import load_env_file

DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / 'schemas' / 'project-mapping.json'
FIELDS = {'code','name','status','client','location','contract_value_usd','planned_start','planned_finish',
          'revised_finish','reporting_date','baseline_progress','revised_progress','actual_progress'}

def normalized(value):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w%]+', ' ', str(value or '').strip().lower().replace('_',' '))).strip()

class FieldMapping(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    description: str = Field(default='', max_length=500)
    aliases: list[str] = Field(default_factory=list, max_length=50)
    column: int | None = Field(default=None, ge=1, le=100)
    infer_unlabeled: bool = False
    value_map: dict[str,str] = Field(default_factory=dict)
    progress_unit: Literal['excel','percent','fraction'] = 'excel'
    source_currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    usd_rate: float | None = Field(default=None, gt=0, le=1000000)

class ProjectMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    profile_id: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1,max_length=200)
    sheet: int | str = 0
    header_row: int | None = Field(default=None,ge=1,le=30)
    data_start_row: int | None = Field(default=None,ge=1,le=2000)
    date_format: Literal['iso','day_first','month_first'] = 'iso'
    fields: dict[str,FieldMapping] = Field(json_schema_extra={'propertyNames':{'enum':sorted(FIELDS)},'required':['code','name']})

    @model_validator(mode='after')
    def validate_mapping(self):
        if set(self.fields)-FIELDS or not {'code','name'} <= set(self.fields):
            raise ValueError('Use supported project fields and include code and name mappings')
        if isinstance(self.sheet,int) and not 0<=self.sheet<100:
            raise ValueError('Sheet index must be between 0 and 99')
        if self.header_row and self.data_start_row and self.data_start_row<=self.header_row:
            raise ValueError('Data must start after the header row')
        columns=[rule.column for rule in self.fields.values() if rule.column]
        if len(columns)!=len(set(columns)):raise ValueError('Each source column may map to only one project field')
        aliases={}
        for field,rule in self.fields.items():
            if rule.infer_unlabeled and field!='code':
                raise ValueError('Automatic unlabeled inference supports project codes only; configure a column for other unlabeled fields')
            if (rule.source_currency or rule.usd_rate is not None) and field!='contract_value_usd':
                raise ValueError('Currency settings only apply to contract_value_usd')
            if rule.usd_rate is not None and not rule.source_currency:
                raise ValueError('Declare the source currency for a conversion rate')
            if rule.source_currency=='USD' and rule.usd_rate not in (None,1):
                raise ValueError('USD source values cannot use a non-unit USD conversion rate')
            for alias in rule.aliases:
                key=normalized(alias)
                if not key or len(alias)>200:raise ValueError('Aliases must contain 1–200 meaningful characters')
                if key in aliases and aliases[key]!=field:raise ValueError('An alias cannot identify multiple fields')
                aliases[key]=field
        return self

def load_mapping(path=None):
    load_env_file()
    selected=Path(path or os.environ.get('PROSIGHT_PROJECT_MAPPING_PATH') or DEFAULT_PROFILE)
    try:
        if selected.stat().st_size>65536:raise ValueError('Mapping profile exceeds 64 KB')
        return ProjectMapping.model_validate_json(selected.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError) as error:
        raise ValueError('Invalid project mapping profile: '+(str(error) if isinstance(error,ValueError) else 'file cannot be read')) from error

def fingerprint(profile):
    return hashlib.sha256(json.dumps(profile.model_dump(),sort_keys=True).encode()).hexdigest()

def column_mapping(headers, samples, profile):
    names=[normalized(value) for value in headers]
    mapping={};methods={};warnings=[]
    for field,rule in profile.fields.items():
        matches=[i for i,name in enumerate(names) if name and name in {normalized(alias) for alias in rule.aliases}]
        if rule.column:
            matches=[rule.column-1];method='configured column'
        else:method='header alias'
        if len(matches)>1:raise ValueError(f'Multiple columns map to {field}; configure one source column in the JSON profile')
        if matches:mapping[field]=matches[0];methods[field]=method
    for field,rule in profile.fields.items():
        if field in mapping or not rule.infer_unlabeled:continue
        candidates=[]
        for index,name in enumerate(names):
            if name or index in mapping.values():continue
            values=[row[index].value for row in samples if index<len(row) and row[index].value is not None]
            if values and all(isinstance(value,str) and re.fullmatch(r'(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+',value.strip()) for value in values):
                candidates.append(index)
        if len(candidates)==1:
            mapping[field]=candidates[0];methods[field]='inferred from unlabeled project-code values'
            warnings.append('Project code was inferred from an unlabeled column. Verify its mapping before confirmation.')
        elif candidates:warnings.append('Unlabeled project-code columns are ambiguous. Configure the correct column in the JSON profile.')
    if len(mapping.values())!=len(set(mapping.values())):raise ValueError('A column maps to multiple fields; correct the mapping profile')
    return mapping,methods,warnings

def transform(value,field,cell,header,profile):
    rule=profile.fields[field]
    if isinstance(value,str):
        value=value.strip()
        value=rule.value_map.get(value,rule.value_map.get(value.lower(),value))
    if field in {'planned_start','planned_finish','revised_finish','reporting_date'} and isinstance(value,str):
        try:return datetime.strptime(value,'%Y-%m-%d').date().isoformat()
        except ValueError:
            if profile.date_format=='iso':raise ValueError('Use an ISO date or configure day_first / month_first')
            fmt='%d/%m/%Y' if profile.date_format=='day_first' else '%m/%d/%Y'
            return datetime.strptime(value.replace('-','/').replace('.','/'),fmt).date().isoformat()
    if field=='contract_value_usd':
        currency=rule.source_currency
        stated=re.findall(r'\b(USD|AED|EUR|GBP|INR|SAR|QAR)\b',str(header).upper())
        if stated and any(code!=currency for code in stated):raise ValueError('Header currency conflicts with the mapping profile')
        if not currency:raise ValueError('Declare the source currency in the mapping profile')
        if currency!='USD' and rule.usd_rate is None:raise ValueError('A verified USD conversion rate is required')
        return float(value)*(rule.usd_rate if rule.usd_rate is not None else 1)
    if field.endswith('progress') and isinstance(value,(int,float)):
        if rule.progress_unit=='fraction' or (rule.progress_unit=='excel' and '%' in cell.number_format):return value*100
    return value
