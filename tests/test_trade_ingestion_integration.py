"""Explicit live-network smoke test for the controlled trade query."""

from __future__ import annotations

import pytest

from app.database.session import SessionLocal
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.sdmx.comtrade_client import ComtradeClient
from app.sdmx.data_parser import parse_comtrade_response
from scripts.ingest_trade_data import CONTROLLED_QUERY


@pytest.mark.integration
def test_live_tunisia_trade_record_parses_and_normalizes_without_writes() -> None:
    period = CONTROLLED_QUERY.periods[0]
    with ComtradeClient(timeout_seconds=30.0) as client:
        payload = client.get_trade_data(
            type_code=CONTROLLED_QUERY.type_code,
            frequency_code=CONTROLLED_QUERY.frequency_code,
            classification_code=CONTROLLED_QUERY.classification_code,
            parameters=CONTROLLED_QUERY.request_parameters(period),
        )
    parsed = parse_comtrade_response(payload)
    assert parsed.record_count == 1
    with SessionLocal() as session:
        result = normalize_trade_observation(parsed.observations[0], session)
    assert result.observation is not None
    assert result.observation.reference_iso3 == "TUN"
    assert result.observation.reference_is_au_member is True
    assert result.observation.counterpart_name == "World"
