"""Deterministic observation identity and revision-content tests."""

from __future__ import annotations

from decimal import Decimal

from app.database.models import AreaType
from app.pipelines.observation_identity import (
    build_dataset_identity,
    build_observation_content,
    build_source_key,
    hash_observation_content,
    hash_source_key,
    identify_observation,
)
from app.pipelines.trade_models import NormalizedTradeObservation


DATASET_IDENTITY = build_dataset_identity("UNSD", "IMTS_A", "1.0")


def _observation(**changes: object) -> NormalizedTradeObservation:
    values: dict[str, object] = {
        "source_agency": "UNSD",
        "source_system": "UN_COMTRADE",
        "source_dataflow": "IMTS_A",
        "source_dataflow_version": "1.0",
        "source_dsd": "IMTS",
        "source_dsd_version": "1.2",
        "reference_area_source_code": "788",
        "reference_geo_id": 1,
        "reference_iso2": "TN",
        "reference_iso3": "TUN",
        "reference_name": "Tunisia",
        "reference_area_type": AreaType.COUNTRY,
        "reference_is_au_member": True,
        "counterpart_area_source_code": "0",
        "counterpart_geo_id": 2,
        "counterpart_name": "World",
        "counterpart_area_type": AreaType.AGGREGATE,
        "counterpart_is_au_member": False,
        "trade_flow_code": "M",
        "frequency_code": "A",
        "commodity_code": "TOTAL",
        "commodity_classification": "S4",
        "commodity_sdmx_code": "SITC4_TOTAL",
        "time_period": "2022",
        "primary_value": Decimal("100"),
        "quantity": Decimal("2.00"),
        "net_weight": Decimal("3.0"),
        "gross_weight": Decimal("4"),
        "cif_value": Decimal("100"),
        "fob_value": None,
        "source_dimensions": {
            "FREQ": "A",
            "REF_AREA": "TN",
            "TRADE_FLOW": "M",
            "COMMODITY_1": "SITC4_TOTAL",
            "COUNTERPART_AREA_1": "W0",
            "COUNTERPART_AREA_2": "W0",
        },
        "source_attributes": {
            "qtyUnitCode": 8,
            "isReported": False,
            "flowDesc": "Import",
        },
        "source_fields": {"elapsedTime": "not an observation field"},
    }
    values.update(changes)
    return NormalizedTradeObservation.model_validate(values)


def _changed_dimension(
    observation: NormalizedTradeObservation, concept_id: str, value: str
) -> NormalizedTradeObservation:
    changed = observation.model_copy(deep=True)
    changed.source_dimensions[concept_id] = value
    return changed


def test_same_observation_has_same_source_key_and_hashes() -> None:
    first = identify_observation(_observation())
    second = identify_observation(_observation())

    assert first.source_key == second.source_key
    assert first.source_key_hash == second.source_key_hash
    assert first.observation_content_hash == second.observation_content_hash


def test_source_key_is_sorted_and_includes_time_exactly_once() -> None:
    observation = _observation()
    observation.source_dimensions["TIME_PERIOD"] = "ignored-duplicate"

    key = build_source_key(observation)

    assert key == (
        "COMMODITY_1=SITC4_TOTAL|COUNTERPART_AREA_1=W0|"
        "COUNTERPART_AREA_2=W0|FREQ=A|REF_AREA=TN|TIME_PERIOD=2022|"
        "TRADE_FLOW=M"
    )
    assert key.count("TIME_PERIOD=") == 1


def test_revision_keeps_identity_and_changes_content_hash() -> None:
    original = _observation(primary_value=Decimal("100"))
    revised = original.model_copy(update={"primary_value": Decimal("110")})

    original_identity = identify_observation(original)
    revised_identity = identify_observation(revised)

    assert original_identity.source_key_hash == revised_identity.source_key_hash
    assert (
        original_identity.observation_content_hash
        != revised_identity.observation_content_hash
    )


def test_different_time_period_changes_source_key_hash() -> None:
    original = _observation()
    changed = original.model_copy(update={"time_period": "2023"})
    assert identify_observation(original).source_key_hash != identify_observation(
        changed
    ).source_key_hash


def test_different_reporter_changes_source_key_hash() -> None:
    original = _observation()
    changed = _changed_dimension(original, "REF_AREA", "KE")
    assert identify_observation(original).source_key_hash != identify_observation(
        changed
    ).source_key_hash


def test_different_partner_changes_source_key_hash() -> None:
    original = _observation()
    changed = _changed_dimension(original, "COUNTERPART_AREA_1", "KE")
    assert identify_observation(original).source_key_hash != identify_observation(
        changed
    ).source_key_hash


def test_different_trade_flow_changes_source_key_hash() -> None:
    original = _observation()
    changed = _changed_dimension(original, "TRADE_FLOW", "X")
    assert identify_observation(original).source_key_hash != identify_observation(
        changed
    ).source_key_hash


def test_different_commodity_changes_source_key_hash() -> None:
    original = _observation()
    changed = _changed_dimension(original, "COMMODITY_1", "SITC4_01")
    assert identify_observation(original).source_key_hash != identify_observation(
        changed
    ).source_key_hash


def test_different_dataset_changes_source_key_hash() -> None:
    source_key = build_source_key(_observation())
    other_dataset = build_dataset_identity("UNSD", "IMTS_A", "2.0")

    assert hash_source_key(DATASET_IDENTITY, source_key) != hash_source_key(
        other_dataset, source_key
    )


def test_dictionary_order_does_not_change_hashes() -> None:
    original = _observation()
    reordered = original.model_copy(deep=True)
    reordered.source_dimensions = dict(reversed(original.source_dimensions.items()))
    reordered.source_attributes = dict(reversed(original.source_attributes.items()))

    assert identify_observation(original) == identify_observation(reordered)


def test_volatile_api_envelope_metadata_has_no_effect() -> None:
    first = _observation(source_fields={"api_envelope": {"elapsedTime": "0.05"}})
    second = _observation(source_fields={"api_envelope": {"elapsedTime": "9.99"}})

    assert identify_observation(first) == identify_observation(second)


def test_decimal_scale_is_canonicalized_by_numeric_equivalence() -> None:
    first = _observation(primary_value=Decimal("1.0"), quantity=Decimal("2.00"))
    second = _observation(primary_value=Decimal("1.00"), quantity=Decimal("2.0"))

    assert build_observation_content(first) == build_observation_content(second)
    assert hash_observation_content(first) == hash_observation_content(second)
