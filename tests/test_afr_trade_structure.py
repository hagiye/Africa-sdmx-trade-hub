"""Canonical AFR_TRADE definition and shared-registry loader tests."""

from __future__ import annotations

import copy

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.pipelines.afr_trade_structure import (
    EXPECTED_DISCLAIMER,
    load_afr_trade_structure,
    load_canonical_structure,
    structure_checksum,
)


EXPECTED_DIMENSIONS = (
    "FREQ",
    "REF_AREA",
    "COUNTERPART_AREA",
    "TRADE_FLOW",
    "PRODUCT_SCHEME",
    "PRODUCT",
    "UNIT_MEASURE",
    "TIME_PERIOD",
)


def _model() -> dict:
    return load_canonical_structure().definition


def test_target_identities_and_disclaimer_are_explicit() -> None:
    model = _model()

    assert model["agency"]["id"] == "AFRSTAT"
    assert model["dataflow"]["id"] == "AFR_TRADE"
    assert model["dataflow"]["version"] == "1.0"
    assert model["dsd"]["id"] == "AFR_TRADE"
    assert model["dsd"]["version"] == "1.0"
    assert model["concept_scheme"]["id"] == "CS_AFR_TRADE"
    assert model["concept_scheme"]["version"] == "1.0"
    assert model["disclaimer"] == EXPECTED_DISCLAIMER
    assert model["is_sdmx_ml"] is False


def test_dimensions_have_required_deterministic_order() -> None:
    dimensions = _model()["dsd"]["dimensions"]

    assert tuple(item["id"] for item in dimensions) == EXPECTED_DIMENSIONS
    assert [item["position"] for item in dimensions] == list(range(1, 9))
    assert all(item["required"] is True for item in dimensions)
    assert dimensions[-1]["role"] == "time"


def test_primary_measure_and_attributes_use_declared_concepts() -> None:
    model = _model()
    concept_ids = {
        item["id"] for item in model["concept_scheme"]["concepts"]
    }
    measure = model["dsd"]["measures"]
    attributes = model["dsd"]["attributes"]

    assert [item["id"] for item in measure] == ["OBS_VALUE"]
    assert measure[0]["role"] == "primary_measure"
    assert {item["id"] for item in attributes} == {
        "OBS_STATUS",
        "CONF_STATUS",
        "UNIT_MULT",
        "DECIMALS",
        "SOURCE",
    }
    assert set(EXPECTED_DIMENSIONS) | {item["id"] for item in attributes} | {
        "OBS_VALUE"
    } == concept_ids


def test_all_codelist_references_resolve_and_codes_are_unique() -> None:
    model = _model()
    codelists = {
        ("AFRSTAT", item["id"], item["version"]): item
        for item in model["codelists"]
    }

    for component in (
        model["dsd"]["dimensions"] + model["dsd"]["attributes"]
    ):
        reference = component.get("codelist")
        if reference is not None:
            assert (
                reference["agency"],
                reference["id"],
                reference["version"],
            ) in codelists
    for codelist in codelists.values():
        codes = [item["id"] for item in codelist["codes"]]
        assert len(codes) == len(set(codes))


def test_every_structure_concept_codelist_and_code_has_bilingual_labels() -> None:
    model = _model()
    labeled_items = [
        model["agency"],
        model["dataflow"],
        model["dsd"],
        model["concept_scheme"],
        *model["concept_scheme"]["concepts"],
        *model["codelists"],
        *(code for item in model["codelists"] for code in item["codes"]),
    ]

    assert all(item["labels"]["en"] for item in labeled_items)
    assert all(item["labels"]["fr"] for item in labeled_items)


def test_area_codelist_reuses_au_geography_and_world_is_not_a_country() -> None:
    area = next(
        item for item in _model()["codelists"] if item["id"] == "CL_AFR_AREA"
    )
    countries = [
        code
        for code in area["codes"]
        if code["annotations"]["area_type"] == "COUNTRY"
    ]
    world = next(code for code in area["codes"] if code["id"] == "AFR_WORLD")

    assert len(countries) == 55
    assert all(len(code["id"]) == 2 for code in countries)
    assert all(code["annotations"]["is_iso_country"] is True for code in countries)
    assert world["annotations"] == {
        "area_type": "AGGREGATE",
        "is_iso_country": False,
    }
    assert world["id"] not in {code["id"] for code in countries}


def test_product_pair_preserves_classification_context() -> None:
    model = _model()
    product_scheme = next(
        item for item in model["codelists"] if item["id"] == "CL_PRODUCT_SCHEME"
    )
    product = next(
        item for item in model["codelists"] if item["id"] == "CL_PRODUCT"
    )

    assert [code["id"] for code in product_scheme["codes"]] == ["SITC4"]
    assert [code["id"] for code in product["codes"]] == ["TOTAL"]
    assert "PRODUCT_SCHEME" in EXPECTED_DIMENSIONS


def test_structure_checksum_is_deterministic_and_change_sensitive() -> None:
    first = load_canonical_structure()
    second = load_canonical_structure()
    changed = copy.deepcopy(first.definition)
    changed["dsd"]["labels"]["en"] += " changed"

    assert first.checksum == second.checksum
    assert first.checksum == structure_checksum(first.definition)
    assert structure_checksum(changed) != first.checksum


def test_loader_is_idempotent_and_resolves_registry_graph(db_session: Session) -> None:
    first = load_afr_trade_structure(db_session)
    first_counts = {
        model: db_session.scalar(select(func.count()).select_from(model)) or 0
        for model in (
            db.Agency,
            db.Dataflow,
            db.DSD,
            db.ConceptScheme,
            db.Concept,
            db.Codelist,
            db.Code,
            db.Dimension,
            db.Attribute,
            db.Measure,
        )
    }
    second = load_afr_trade_structure(db_session)
    second_counts = {
        model: db_session.scalar(select(func.count()).select_from(model)) or 0
        for model in first_counts
    }

    assert first.action == "INSERT"
    assert first.inserted == 14
    assert first.updated == first.unchanged == 0
    assert first.codes == 70
    assert second.action == "UNCHANGED"
    assert second.unchanged == 14
    assert second.inserted == second.updated == 0
    assert second.checksum == first.checksum
    assert second_counts == first_counts

    dataflow = db_session.scalar(select(db.Dataflow))
    dsd = db_session.scalar(select(db.DSD))
    scheme = db_session.scalar(select(db.ConceptScheme))
    assert dataflow is not None and dsd is not None and scheme is not None
    assert (
        dataflow.dsd_agency_id,
        dataflow.dsd_id,
        dataflow.dsd_version,
    ) == ("AFRSTAT", "AFR_TRADE", "1.0")
    assert dataflow.description == EXPECTED_DISCLAIMER
    assert tuple(item.concept_id for item in dsd.dimensions) == EXPECTED_DIMENSIONS
    assert [item.concept_id for item in dsd.measures] == ["OBS_VALUE"]
    assert len(scheme.concepts) == 14

    codelist_identities = {
        (row.agency_id, row.codelist_id, row.version)
        for row in db_session.scalars(select(db.Codelist))
    }
    for component in (*dsd.dimensions, *dsd.attributes):
        if component.codelist_id:
            assert (
                component.codelist_agency_id,
                component.codelist_id,
                component.codelist_version,
            ) in codelist_identities


def test_loader_creates_structure_only_not_data_or_mappings(
    db_session: Session,
) -> None:
    load_afr_trade_structure(db_session)

    assert db_session.scalar(select(func.count()).select_from(db.StatDataset)) == 0
    assert db_session.scalar(select(func.count()).select_from(db.TradeObservation)) == 0
    assert db_session.scalar(select(func.count()).select_from(db.SourceGeoMapping)) == 0
