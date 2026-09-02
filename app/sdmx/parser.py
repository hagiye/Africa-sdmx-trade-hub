"""SDMX-ML structure parsers for the provider's SDMX 3.0 responses."""

from __future__ import annotations

import re

from lxml import etree

from app.sdmx.exceptions import SDMXParseError
from app.sdmx.models import (
    Code,
    Codelist,
    Component,
    Concept,
    ConceptScheme,
    Dataflow,
    DataStructure,
    Labels,
    StructureRef,
)

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
URN_RE = re.compile(
    r"urn:sdmx:org\.sdmx\.infomodel\.[^.]+\.(?P<type>[^=]+)="
    r"(?P<agency>[^:]+):(?P<id>[^(.]+)\((?P<version>[^)]+)\)"
)


def _local(element: etree._Element) -> str:
    return etree.QName(element).localname


def _children(element: etree._Element, name: str) -> list[etree._Element]:
    return [child for child in element if _local(child) == name]


def _descendants(element: etree._Element, name: str) -> list[etree._Element]:
    return [child for child in element.iter() if _local(child) == name]


def _one_child(element: etree._Element, name: str) -> etree._Element | None:
    return next((child for child in element if _local(child) == name), None)


def _text(element: etree._Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def _labels(element: etree._Element, child_name: str = "Name") -> Labels:
    result: Labels = {}
    for child in _children(element, child_name):
        value = _text(child)
        if value:
            result[child.get(XML_LANG, "und")] = value
    return result


def _root(payload: bytes) -> etree._Element:
    if not payload or not payload.strip():
        raise SDMXParseError("SDMX response is empty")
    try:
        return etree.fromstring(
            payload,
            parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True),
        )
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise SDMXParseError(f"Invalid SDMX XML: {exc}") from exc


def parse_structure_ref(value: str | None) -> StructureRef | None:
    if not value:
        return None
    match = URN_RE.search(value.strip())
    if not match:
        return None
    kind = match.group("type")
    aliases = {
        "DataStructure": "datastructure",
        "Dataflow": "dataflow",
        "Codelist": "codelist",
        "ConceptScheme": "conceptscheme",
        "Concept": "conceptscheme",
    }
    return StructureRef(
        aliases.get(kind, kind.lower()),
        match.group("agency"),
        match.group("id"),
        match.group("version"),
    )


def _maintainable(element: etree._Element) -> tuple[str, str, str]:
    try:
        return element.attrib["agencyID"], element.attrib["id"], element.get("version", "1.0")
    except KeyError as exc:
        raise SDMXParseError(f"{_local(element)} is missing a required identity") from exc


def parse_dataflows(payload: bytes) -> list[Dataflow]:
    root = _root(payload)
    result: list[Dataflow] = []
    for element in _descendants(root, "Dataflow"):
        agency, structure_id, version = _maintainable(element)
        reference = parse_structure_ref(_text(_one_child(element, "Structure")))
        result.append(
            Dataflow(
                agency,
                structure_id,
                version,
                _labels(element),
                _labels(element, "Description"),
                reference,
                element.get("isExternalReference", "false").lower() == "true",
            )
        )
    return result


def _representation(element: etree._Element) -> tuple[str | None, StructureRef | None]:
    local_rep = _one_child(element, "LocalRepresentation")
    if local_rep is None:
        return None, None
    enumeration = _one_child(local_rep, "Enumeration")
    if enumeration is not None:
        value = _text(enumeration)
        ref = parse_structure_ref(value)
        return value, ref if ref and ref.structure_type == "codelist" else None
    text_format = _one_child(local_rep, "TextFormat")
    if text_format is not None:
        details = ", ".join(f"{key}={value}" for key, value in sorted(text_format.attrib.items()))
        return f"TextFormat({details})", None
    return None, None


def _concept_scheme_ref(element: etree._Element) -> StructureRef | None:
    identity = _text(_one_child(element, "ConceptIdentity"))
    ref = parse_structure_ref(identity)
    if ref:
        return StructureRef("conceptscheme", ref.agency, ref.structure_id, ref.version)
    return None


def _attribute_attachment(element: etree._Element) -> str | None:
    relationship = _one_child(element, "AttributeRelationship")
    if relationship is None or len(relationship) == 0:
        return None
    child = relationship[0]
    value = _text(child)
    return f"{_local(child)}:{value}" if value else _local(child)


def parse_dsd(payload: bytes) -> DataStructure:
    root = _root(payload)
    elements = _descendants(root, "DataStructure")
    if not elements:
        raise SDMXParseError("No DataStructure found in SDMX response")
    element = elements[0]
    agency, structure_id, version = _maintainable(element)
    dsd = DataStructure(
        agency,
        structure_id,
        version,
        _labels(element),
        _labels(element, "Description"),
    )
    dimension_elements = [
        child
        for container in _descendants(element, "DimensionList")
        for child in container
        if _local(child) in {"Dimension", "TimeDimension"}
    ]
    for child in dimension_elements:
        representation, codelist = _representation(child)
        role = "time" if _local(child) == "TimeDimension" else "dimension"
        position = int(child.attrib["position"]) if child.get("position") else None
        dsd.dimensions.append(
            Component(child.attrib["id"], role, representation, codelist, position)
        )
        concept_ref = _concept_scheme_ref(child)
        if concept_ref:
            dsd.concept_schemes.add(concept_ref)
        if codelist:
            dsd.codelists.add(codelist)
        else:
            enum = _one_child(_one_child(child, "LocalRepresentation"), "Enumeration") if _one_child(child, "LocalRepresentation") is not None else None
            enum_ref = parse_structure_ref(_text(enum))
            if enum_ref and enum_ref.structure_type == "conceptscheme":
                dsd.concept_schemes.add(enum_ref)
    for child in _descendants(element, "Attribute"):
        representation, codelist = _representation(child)
        dsd.attributes.append(
            Component(
                child.attrib["id"],
                "attribute",
                representation,
                codelist,
                attachment_level=_attribute_attachment(child),
            )
        )
        concept_ref = _concept_scheme_ref(child)
        if concept_ref:
            dsd.concept_schemes.add(concept_ref)
        if codelist:
            dsd.codelists.add(codelist)
    for container in _descendants(element, "MeasureList"):
        for child in _children(container, "Measure"):
            representation, codelist = _representation(child)
            dsd.measures.append(
                Component(child.attrib["id"], "measure", representation, codelist)
            )
            concept_ref = _concept_scheme_ref(child)
            if concept_ref:
                dsd.concept_schemes.add(concept_ref)
    return dsd


def parse_concept_schemes(payload: bytes) -> list[ConceptScheme]:
    root = _root(payload)
    result: list[ConceptScheme] = []
    for element in _descendants(root, "ConceptScheme"):
        agency, structure_id, version = _maintainable(element)
        scheme = ConceptScheme(
            agency,
            structure_id,
            version,
            _labels(element),
            _labels(element, "Description"),
        )
        for child in _children(element, "Concept"):
            scheme.concepts.append(
                Concept(
                    child.attrib["id"],
                    _labels(child),
                    _labels(child, "Description"),
                )
            )
        result.append(scheme)
    return result


def parse_codelists(payload: bytes) -> list[Codelist]:
    root = _root(payload)
    result: list[Codelist] = []
    for element in _descendants(root, "Codelist"):
        agency, structure_id, version = _maintainable(element)
        codelist = Codelist(
            agency,
            structure_id,
            version,
            _labels(element),
            _labels(element, "Description"),
        )
        for child in _children(element, "Code"):
            codelist.codes.append(
                Code(
                    child.attrib["id"],
                    _labels(child),
                    _labels(child, "Description"),
                    _text(_one_child(child, "Parent")),
                )
            )
        result.append(codelist)
    return result


def parse_constraints(payload: bytes) -> list[StructureRef]:
    """Return identities for data/content constraints in a structure message."""
    root = _root(payload)
    result: list[StructureRef] = []
    for element in root.iter():
        local_name = _local(element)
        if local_name not in {"DataConstraint", "ContentConstraint"}:
            continue
        agency, structure_id, version = _maintainable(element)
        result.append(StructureRef("dataconstraint", agency, structure_id, version))
    return result
