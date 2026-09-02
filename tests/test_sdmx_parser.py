"""Parser tests using a compact representative SDMX-ML 3.0 response."""

import pytest

from app.sdmx.exceptions import SDMXParseError
from app.sdmx.parser import (
    parse_codelists,
    parse_concept_schemes,
    parse_constraints,
    parse_dataflows,
    parse_dsd,
)


def test_parse_dataflow_and_multilingual_labels(structure_payload: bytes) -> None:
    flow = parse_dataflows(structure_payload)[0]

    assert (flow.agency, flow.structure_id, flow.version) == (
        "UNSD",
        "IMTS_A",
        "1.0",
    )
    assert flow.labels == {
        "en": "IMTS Annual",
        "fr": "Commerce international annuel",
    }
    assert flow.structure.structure_id == "IMTS"
    assert flow.structure.version == "1.2"


def test_parse_dsd_components_and_references(structure_payload: bytes) -> None:
    dsd = parse_dsd(structure_payload)

    assert (dsd.agency, dsd.structure_id, dsd.version) == ("UNSD", "IMTS", "1.2")
    assert [(item.concept_id, item.position, item.role) for item in dsd.dimensions] == [
        ("FREQ", 1, "dimension"),
        ("TIME_PERIOD", None, "time"),
    ]
    assert dsd.dimensions[0].codelist.structure_id == "CL_FREQ"
    assert dsd.attributes[0].attachment_level == "Observation"
    assert dsd.measures[0].concept_id == "OBS_VALUE"
    assert "textType=Decimal" in dsd.measures[0].representation
    assert {(item.agency, item.structure_id) for item in dsd.concept_schemes} == {
        ("UNSD", "CS_IMTS")
    }


def test_parse_concepts(structure_payload: bytes) -> None:
    scheme = parse_concept_schemes(structure_payload)[0]

    assert scheme.structure_id == "CS_IMTS"
    assert scheme.labels["fr"] == "Concepts IMTS"
    assert [item.concept_id for item in scheme.concepts] == ["FREQ", "OBS_VALUE"]
    assert scheme.concepts[0].labels["fr"] == "Frequence"


def test_parse_codelist_codes_and_parent(structure_payload: bytes) -> None:
    codelist = parse_codelists(structure_payload)[0]

    assert (codelist.agency, codelist.structure_id, codelist.version) == (
        "SDMX",
        "CL_FREQ",
        "2.0",
    )
    assert [item.code for item in codelist.codes] == ["A", "M"]
    assert codelist.codes[0].labels["fr"] == "Annuel"
    assert codelist.codes[1].parent_code == "A"


def test_parse_constraints(structure_payload: bytes) -> None:
    constraints = parse_constraints(structure_payload)

    assert len(constraints) == 1
    assert constraints[0].structure_id == "IMTS_CONSTRAINT"


@pytest.mark.parametrize("payload", [b"", b"<broken"])
def test_invalid_or_empty_xml_raises_parse_error(payload: bytes) -> None:
    with pytest.raises(SDMXParseError):
        parse_dataflows(payload)
