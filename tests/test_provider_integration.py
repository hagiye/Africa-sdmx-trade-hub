"""Explicit live-provider smoke tests."""

import pytest

from app.sdmx.client import SDMXClient
from app.sdmx.discovery import PROVIDER_BASE_URL, SDMXDiscovery, TRADE_DATAFLOW


@pytest.mark.integration
def test_selected_live_dataflow_resolves_to_trade_dsd() -> None:
    discovery = SDMXDiscovery(SDMXClient(PROVIDER_BASE_URL, timeout=30))

    flows, response = discovery.get_dataflows(
        TRADE_DATAFLOW.agency,
        TRADE_DATAFLOW.structure_id,
        TRADE_DATAFLOW.version,
    )

    assert response.status_code == 200
    selected = next(item for item in flows if item.structure_id == "IMTS_A")
    assert (selected.structure.agency, selected.structure.structure_id) == (
        "UNSD",
        "IMTS",
    )
