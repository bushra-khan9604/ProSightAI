"""Platform-owned ingestion catalog and organization mapping compiler.

The catalog is application code/configuration, not tenant input.  Organization
profiles may name source sheets and headers, but cannot select SQL objects,
types, business keys, or security/lineage columns.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .governed_excel import FieldSpec, OrganizationMapping, SheetMapping


LogicalType = Literal[
    "text", "date", "datetime", "decimal", "integer", "currency", "uuid", "boolean"
]


class CatalogField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: LogicalType
    required: bool = False
    scale: int | None = Field(default=None, ge=0, le=12)
    label: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=50)


class CatalogEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    table: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    requires_project_id: bool
    business_key: list[str] = Field(min_length=1)
    sheet_aliases: list[str] = Field(min_length=1, max_length=50)
    fields: dict[str, CatalogField]

    @model_validator(mode="after")
    def validate_business_key(self):
        user_fields = {name for name in self.business_key if name not in {"organization_id", "project_id"}}
        if not user_fields <= set(self.fields):
            raise ValueError("Business-key fields must exist in the canonical field catalog")
        return self


class ConstructionIngestionCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    catalog_version: int = Field(ge=1)
    schema_name: Literal["construction"] = Field(alias="schema")
    entities: dict[str, CatalogEntity]


class OrganizationSheetProfile(BaseModel):
    """The only sheet/column controls accepted from an organization."""

    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(min_length=1, max_length=100)
    sheet_name: str = Field(min_length=1, max_length=250)
    sheet_aliases: list[str] = Field(default_factory=list, max_length=50)
    columns: dict[str, str | list[str]]


def _schema_path(name: str) -> Path:
    return Path(__file__).parents[1] / "schemas" / name


@lru_cache(maxsize=1)
def load_catalog() -> ConstructionIngestionCatalog:
    try:
        payload = json.loads(
            _schema_path("construction-ingestion-catalog.json").read_text(encoding="utf-8")
        )
        return ConstructionIngestionCatalog.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise RuntimeError("The platform construction ingestion catalog is invalid") from error


def organization_profile_json_schema() -> dict:
    """Return the JSON Schema organizations can use to build profile versions."""
    return json.loads(
        _schema_path("organization-ingestion-profile.schema.json").read_text(encoding="utf-8")
    )


def compile_sheet_profile(
    definition: OrganizationSheetProfile,
    *,
    catalog: ConstructionIngestionCatalog | None = None,
) -> SheetMapping:
    """Compile a tenant-controlled label overlay into a governed sheet mapping."""
    selected_catalog = catalog or load_catalog()
    entity = selected_catalog.entities.get(definition.entity_type)
    if entity is None:
        raise ValueError(f"Unsupported governed publication entity: {definition.entity_type}")
    if not definition.columns:
        raise ValueError("An organization sheet profile must map at least one column")

    primary_columns: dict[str, str] = {}
    column_aliases: dict[str, tuple[str, ...]] = {}
    for target, configured in definition.columns.items():
        canonical = entity.fields.get(target)
        if canonical is None:
            raise ValueError(
                f"{definition.entity_type}.{target} is not an organization-configurable import field"
            )
        values = [configured] if isinstance(configured, str) else list(configured)
        values = [value.strip() for value in values if isinstance(value, str) and value.strip()]
        if not values:
            raise ValueError(f"{definition.entity_type}.{target} needs at least one source label")
        normalized = [" ".join(value.split()).casefold() for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{definition.entity_type}.{target} contains duplicate source labels")
        primary_columns[target] = values[0]
        column_aliases[target] = tuple(values[1:])

    missing_required = [
        name for name, field in entity.fields.items() if field.required and name not in primary_columns
    ]
    if missing_required:
        raise ValueError(
            f"{definition.entity_type} mapping is missing required fields: "
            + ", ".join(sorted(missing_required))
        )

    claimed: dict[str, str] = {}
    for target, primary in primary_columns.items():
        for label in (primary, *column_aliases[target]):
            key = " ".join(label.split()).casefold()
            previous = claimed.get(key)
            if previous and previous != target:
                raise ValueError(f"Source label {label!r} maps to multiple canonical fields")
            claimed[key] = target

    fields = {
        name: FieldSpec(kind=entity.fields[name].kind,
                        required=entity.fields[name].required,
                        scale=entity.fields[name].scale)
        for name in primary_columns
    }
    aliases = tuple(dict.fromkeys(
        [alias.strip() for alias in definition.sheet_aliases if alias.strip()]
    ))
    return SheetMapping(
        entity_type=definition.entity_type,
        sheet_name=definition.sheet_name.strip(),
        columns=primary_columns,
        fields=fields,
        business_key=tuple(
            name for name in entity.business_key if name not in {"organization_id", "project_id"}
        ),
        sheet_aliases=aliases,
        column_aliases=column_aliases,
    )


def default_project_sheet() -> OrganizationSheetProfile:
    catalog = load_catalog()
    entity = catalog.entities["projects"]
    columns = {
        name: list(dict.fromkeys([field.label, *field.aliases]))
        for name, field in entity.fields.items()
    }
    return OrganizationSheetProfile(
        entity_type="projects",
        sheet_name=entity.sheet_aliases[0],
        sheet_aliases=entity.sheet_aliases[1:],
        columns=columns,
    )


def validate_compiled_mapping(
    mapping: OrganizationMapping,
    *,
    catalog: ConstructionIngestionCatalog | None = None,
) -> None:
    """Reject persisted/pre-catalog mappings that do not match platform authority."""
    selected_catalog = catalog or load_catalog()
    if mapping.catalog_version != selected_catalog.catalog_version:
        raise ValueError("Mapping profile is not bound to the active construction catalog version")
    for sheet in mapping.sheets:
        entity = selected_catalog.entities.get(sheet.entity_type)
        if entity is None:
            raise ValueError(f"Unsupported governed publication entity: {sheet.entity_type}")
        expected_key = tuple(
            name for name in entity.business_key if name not in {"organization_id", "project_id"}
        )
        supplied_key = tuple(
            name for name in sheet.business_key if name not in {"organization_id", "project_id"}
        )
        if supplied_key != expected_key:
            raise ValueError(f"Business key for {sheet.entity_type} does not match the catalog")
        for name, spec in sheet.fields.items():
            canonical = entity.fields.get(name)
            if canonical is None:
                raise ValueError(f"{sheet.entity_type}.{name} is not a catalog import field")
            if (spec.kind, spec.required, spec.scale) != (
                canonical.kind, canonical.required, canonical.scale
            ):
                raise ValueError(f"{sheet.entity_type}.{name} type rules are platform-controlled")
        missing = [name for name, field in entity.fields.items() if field.required and name not in sheet.fields]
        if missing:
            raise ValueError(
                f"{sheet.entity_type} mapping is missing required fields: "
                + ", ".join(sorted(missing))
            )
