"""Public types for the reusable, version-aware SDMX mapping registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from app.database.models import (
    SdmxCodeMapping,
    SdmxConceptMapping,
    SdmxMappingStatus,
    SdmxMappingType,
    SdmxTransformationDefinition,
)


MappingType = SdmxMappingType
MappingStatus = SdmxMappingStatus


@dataclass(frozen=True)
class StructureIdentity:
    agency: str
    structure_id: str
    version: str

    def display(self) -> str:
        return f"{self.agency}:{self.structure_id}({self.version})"


@dataclass(frozen=True)
class MappingDefinition:
    definition: dict[str, object]
    checksum: str
    path: Path
    mapping_id: str
    mapping_version: str
    source: StructureIdentity
    target: StructureIdentity


T = TypeVar("T")


@dataclass(frozen=True)
class LookupResult(Generic[T]):
    """A safe lookup result that never substitutes an unmapped source value."""

    resolved: bool
    value: T | None = None
    reason: str | None = None


__all__ = [
    "LookupResult",
    "MappingDefinition",
    "MappingStatus",
    "MappingType",
    "SdmxCodeMapping",
    "SdmxConceptMapping",
    "SdmxTransformationDefinition",
    "StructureIdentity",
]
