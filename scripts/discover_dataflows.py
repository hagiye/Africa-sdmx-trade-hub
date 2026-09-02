"""Discover dataflows and report evidence-based merchandise-trade candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.sdmx.client import SDMXClient
from app.sdmx.discovery import SDMXDiscovery

TERMS = ("trade", "merchandise", "international trade", "goods", "imts")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agency", default="all")
    args = parser.parse_args()
    discovery = SDMXDiscovery(
        SDMXClient(settings.sdmx_base_url, settings.sdmx_timeout_seconds)
    )
    flows, response = discovery.get_dataflows(args.agency, "all", "latest")
    rows = []
    print(f"{'Agency':<12} {'ID':<30} {'Version':<10} {'English':<45} French")
    print("-" * 125)
    for flow in sorted(flows, key=lambda item: (item.agency, item.structure_id)):
        name = flow.labels.get("en") or next(iter(flow.labels.values()), "")
        french_name = flow.labels.get("fr", "")
        print(
            f"{flow.agency:<12} {flow.structure_id:<30} {flow.version:<10} "
            f"{name:<45} {french_name}"
        )
        haystack = " ".join(
            [flow.structure_id, *flow.labels.values(), *flow.descriptions.values()]
        ).lower()
        rows.append(
            {
                "agency": flow.agency,
                "id": flow.structure_id,
                "version": flow.version,
                "labels": flow.labels,
                "descriptions": flow.descriptions,
                "structure": (
                    {
                        "agency": flow.structure.agency,
                        "id": flow.structure.structure_id,
                        "version": flow.structure.version,
                    }
                    if flow.structure
                    else None
                ),
                "trade_candidate": any(term in haystack for term in TERMS),
            }
        )
    candidates = [row for row in rows if row["trade_candidate"]]
    print(f"\nTrade candidates found: {len(candidates)}")
    for row in candidates:
        print(f"- {row['agency']}:{row['id']}({row['version']}): {row['labels'].get('en', '')}")
    destination = ROOT / "data" / "discovery" / "dataflows_summary.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "source_url": response.url,
                "checksum": response.checksum,
                "count": len(rows),
                "dataflows": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {destination}")


if __name__ == "__main__":
    main()
