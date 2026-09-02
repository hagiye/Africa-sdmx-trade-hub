"""Inspect the selected live DSD and regenerate its human-readable report."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.sdmx.client import SDMXClient
from app.sdmx.discovery import SDMXDiscovery, TRADE_DSD


def codelist_text(component) -> str:
    if not component.codelist:
        return "-"
    ref = component.codelist
    return f"{ref.agency}:{ref.structure_id}({ref.version})"


def main() -> None:
    discovery = SDMXDiscovery(
        SDMXClient(settings.sdmx_base_url, settings.sdmx_timeout_seconds)
    )
    dsd, response = discovery.get_dsd(TRADE_DSD)
    name = dsd.labels.get("en") or next(iter(dsd.labels.values()), dsd.structure_id)
    print(f"DSD:\n  agency: {dsd.agency}\n  id: {dsd.structure_id}\n  version: {dsd.version}\n  name: {name}")
    print("\nDIMENSIONS:")
    for component in dsd.dimensions:
        print(
            f"  {component.position or '-':>2} {component.concept_id:<30} "
            f"{component.role:<10} {component.representation or '-'}"
        )
    print("\nMEASURES:")
    for component in dsd.measures:
        print(f"  {component.concept_id}: {component.representation or '-'}")
    print("\nATTRIBUTES:")
    for component in dsd.attributes:
        print(
            f"  {component.concept_id}: attachment={component.attachment_level or '-'}; "
            f"representation={component.representation or '-'}"
        )
    time_dimension = next(item for item in dsd.dimensions if item.role == "time")
    primary_measure = dsd.measures[0] if dsd.measures else None
    print(f"\nTIME DIMENSION:\n  {time_dimension.concept_id}")
    print(f"\nPRIMARY MEASURE:\n  {primary_measure.concept_id if primary_measure else '-'}")

    lines = [
        "# Selected trade DSD",
        "",
        f"- Live source: `{response.url}`",
        f"- Structural content SHA-256: `{response.checksum}`",
        f"- Raw payload SHA-256: `{response.raw_checksum}`",
        "",
        f"- Agency: `{dsd.agency}`",
        f"- ID: `{dsd.structure_id}`",
        f"- Version: `{dsd.version}`",
        f"- Name: {name}",
        "",
        "## Dimensions",
        "",
        "| Position | Concept | Role | Representation | Codelist |",
        "|---:|---|---|---|---|",
    ]
    next_position = max((item.position or 0 for item in dsd.dimensions), default=0)
    for component in dsd.dimensions:
        position = component.position
        if position is None:
            next_position += 1
            position = next_position
        lines.append(
            f"| {position} | `{component.concept_id}` | {component.role} | "
            f"`{component.representation or '-'}` | `{codelist_text(component)}` |"
        )
    lines.extend(["", "## Measures", "", "| Concept | Representation |", "|---|---|"])
    lines.extend(
        f"| `{item.concept_id}` | `{item.representation or '-'}` |" for item in dsd.measures
    )
    lines.extend(
        ["", "## Attributes", "", "| Concept | Attachment | Representation | Codelist |", "|---|---|---|---|"]
    )
    lines.extend(
        f"| `{item.concept_id}` | `{item.attachment_level or '-'}` | "
        f"`{item.representation or '-'}` | `{codelist_text(item)}` |"
        for item in dsd.attributes
    )
    lines.extend(
        [
            "",
            f"- Time dimension: `{time_dimension.concept_id}`",
            f"- Primary measure: `{primary_measure.concept_id if primary_measure else '-'}`",
            "",
            "The provider uses SDMX 3.0 `Measure`; the first/only measure is reported as the primary measure for this project's inspection output.",
        ]
    )
    report = ROOT / "docs" / "trade-dsd.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    raw = ROOT / "structures" / "raw" / "UNSD_datastructure_IMTS_1.2.xml"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(response.content)
    print(f"\nSaved {report}\nSaved {raw} ({len(response.content):,} bytes)")


if __name__ == "__main__":
    main()
