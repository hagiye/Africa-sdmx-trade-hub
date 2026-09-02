"""Small internal representations of the SDMX structures used by this project."""

from __future__ import annotations

from dataclasses import dataclass, field


Labels = dict[str, str]


@dataclass(frozen=True)
class StructureRef:
    structure_type: str
    agency: str
    structure_id: str
    version: str


@dataclass
class Dataflow:
    agency: str
    structure_id: str
    version: str
    labels: Labels = field(default_factory=dict)
    descriptions: Labels = field(default_factory=dict)
    structure: StructureRef | None = None
    is_external_reference: bool = False


@dataclass
class Component:
    concept_id: str
    role: str
    representation: str | None = None
    codelist: StructureRef | None = None
    position: int | None = None
    attachment_level: str | None = None


@dataclass
class DataStructure:
    agency: str
    structure_id: str
    version: str
    labels: Labels = field(default_factory=dict)
    descriptions: Labels = field(default_factory=dict)
    dimensions: list[Component] = field(default_factory=list)
    attributes: list[Component] = field(default_factory=list)
    measures: list[Component] = field(default_factory=list)
    concept_schemes: set[StructureRef] = field(default_factory=set)
    codelists: set[StructureRef] = field(default_factory=set)


@dataclass
class Concept:
    concept_id: str
    labels: Labels = field(default_factory=dict)
    descriptions: Labels = field(default_factory=dict)


@dataclass
class ConceptScheme:
    agency: str
    structure_id: str
    version: str
    labels: Labels = field(default_factory=dict)
    descriptions: Labels = field(default_factory=dict)
    concepts: list[Concept] = field(default_factory=list)


@dataclass
class Code:
    code: str
    labels: Labels = field(default_factory=dict)
    descriptions: Labels = field(default_factory=dict)
    parent_code: str | None = None


@dataclass
class Codelist:
    agency: str
    structure_id: str
    version: str
    labels: Labels = field(default_factory=dict)
    descriptions: Labels = field(default_factory=dict)
    codes: list[Code] = field(default_factory=list)
