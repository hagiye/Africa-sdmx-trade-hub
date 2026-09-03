"""Metadata-driven target validation for AFRSTAT:AFR_TRADE(1.0)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import models as db
from app.harmonization.afr_trade_models import (
    AfrTradeObservation,
    HarmonizationIssueCode,
    TargetValidationFinding,
    TargetValidationResult,
    TargetValidationStatus,
)
from app.mappings.sdmx_mapping_models import StructureIdentity
from app.pipelines.afr_trade_structure import load_canonical_structure


@dataclass(frozen=True)
class TargetComponent:
    concept_id: str
    required: bool
    codelist_identity: tuple[str, str, str] | None


@dataclass(frozen=True)
class TargetValidationContext:
    identity: StructureIdentity
    dimensions: tuple[TargetComponent, ...]
    attributes: tuple[TargetComponent, ...]
    measures: tuple[TargetComponent, ...]
    codes: dict[str, frozenset[str]]

    @classmethod
    def from_session(
        cls,
        session: Session,
        identity: StructureIdentity = StructureIdentity("AFRSTAT", "AFR_TRADE", "1.0"),
    ) -> "TargetValidationContext":
        dsd = session.scalar(
            select(db.DSD).where(
                db.DSD.agency_id == identity.agency,
                db.DSD.dsd_id == identity.structure_id,
                db.DSD.version == identity.version,
            )
        )
        if dsd is None:
            raise ValueError(f"Target DSD is not loaded: {identity.display()}")
        canonical = load_canonical_structure().definition
        dsd_definition = canonical["dsd"]
        canonical_identity = StructureIdentity(
            canonical["agency"]["id"],
            dsd_definition["id"],
            dsd_definition["version"],
        )
        if canonical_identity != identity:
            raise ValueError(
                f"Canonical target definition does not match {identity.display()}"
            )

        dimensions_by_id = {row.concept_id: row for row in dsd.dimensions}
        attributes_by_id = {row.concept_id: row for row in dsd.attributes}
        measures_by_id = {row.concept_id: row for row in dsd.measures}

        def component(
            item: dict[str, object], rows: dict[str, object], *, required: bool
        ) -> TargetComponent:
            concept_id = str(item["id"])
            row = rows.get(concept_id)
            if row is None:
                raise ValueError(
                    f"Target registry is missing {concept_id} for {identity.display()}"
                )
            codelist_identity = None
            if getattr(row, "codelist_id", None):
                codelist_identity = (
                    row.codelist_agency_id,
                    row.codelist_id,
                    row.codelist_version,
                )
            return TargetComponent(concept_id, required, codelist_identity)

        dimensions = tuple(
            component(item, dimensions_by_id, required=bool(item["required"]))
            for item in dsd_definition["dimensions"]
        )
        attributes = tuple(
            component(item, attributes_by_id, required=bool(item["required"]))
            for item in dsd_definition["attributes"]
        )
        measures = tuple(
            component(item, measures_by_id, required=True)
            for item in dsd_definition["measures"]
        )

        identities = {
            item.codelist_identity
            for item in (*dimensions, *attributes)
            if item.codelist_identity is not None
        }
        codes: dict[str, frozenset[str]] = {}
        for codelist_identity in identities:
            agency, codelist_id, version = codelist_identity
            row = session.scalar(
                select(db.Codelist).where(
                    db.Codelist.agency_id == agency,
                    db.Codelist.codelist_id == codelist_id,
                    db.Codelist.version == version,
                )
            )
            if row is None:
                raise ValueError(
                    f"Target codelist is not loaded: {agency}:{codelist_id}({version})"
                )
            values = frozenset(code.code for code in row.codes)
            for item in (*dimensions, *attributes):
                if item.codelist_identity == codelist_identity:
                    codes[item.concept_id] = values
        return cls(identity, dimensions, attributes, measures, codes)


FIELD_BY_CONCEPT = {
    "FREQ": "freq",
    "REF_AREA": "ref_area",
    "COUNTERPART_AREA": "counterpart_area",
    "TRADE_FLOW": "trade_flow",
    "PRODUCT_SCHEME": "product_scheme",
    "PRODUCT": "product",
    "UNIT_MEASURE": "unit_measure",
    "TIME_PERIOD": "time_period",
    "OBS_VALUE": "obs_value",
    "OBS_STATUS": "obs_status",
    "CONF_STATUS": "conf_status",
    "UNIT_MULT": "unit_mult",
    "DECIMALS": "decimals",
    "SOURCE": "source",
}


def validate_afr_trade_observation(
    observation: AfrTradeObservation,
    context: TargetValidationContext,
) -> TargetValidationResult:
    findings: list[TargetValidationFinding] = []
    components = (*context.dimensions, *context.attributes, *context.measures)
    for component in components:
        value = getattr(observation, FIELD_BY_CONCEPT[component.concept_id])
        if component.required and value is None:
            findings.append(
                TargetValidationFinding(
                    code=HarmonizationIssueCode.TARGET_VALIDATION_FAILED,
                    concept_id=component.concept_id,
                    message=f"Required target concept {component.concept_id} is missing.",
                )
            )
            continue
        allowed = context.codes.get(component.concept_id)
        if value is not None and allowed is not None and str(value) not in allowed:
            findings.append(
                TargetValidationFinding(
                    code=HarmonizationIssueCode.INVALID_TARGET_CODE,
                    concept_id=component.concept_id,
                    invalid_value=value,
                    message=(
                        f"{value!r} is not in the target codelist for "
                        f"{component.concept_id}."
                    ),
                )
            )

    if observation.time_period is not None:
        patterns = {
            "A": r"^[0-9]{4}$",
            "Q": r"^[0-9]{4}-Q[1-4]$",
            "M": r"^[0-9]{4}-(0[1-9]|1[0-2])$",
        }
        pattern = patterns.get(observation.freq or "")
        if pattern is None or re.fullmatch(pattern, observation.time_period) is None:
            findings.append(
                TargetValidationFinding(
                    code=HarmonizationIssueCode.TARGET_VALIDATION_FAILED,
                    concept_id="TIME_PERIOD",
                    invalid_value=observation.time_period,
                    message="TIME_PERIOD is invalid for the target frequency.",
                )
            )
    if observation.obs_value is not None and (
        not isinstance(observation.obs_value, Decimal)
        or not observation.obs_value.is_finite()
    ):
        findings.append(
            TargetValidationFinding(
                code=HarmonizationIssueCode.TARGET_VALIDATION_FAILED,
                concept_id="OBS_VALUE",
                invalid_value=observation.obs_value,
                message="OBS_VALUE must be a finite Decimal.",
            )
        )
    if observation.decimals is not None and not 0 <= observation.decimals <= 12:
        findings.append(
            TargetValidationFinding(
                code=HarmonizationIssueCode.TARGET_VALIDATION_FAILED,
                concept_id="DECIMALS",
                invalid_value=observation.decimals,
                message="DECIMALS must be between 0 and 12.",
            )
        )
    return TargetValidationResult(
        status=(
            TargetValidationStatus.INVALID
            if findings
            else TargetValidationStatus.VALID
        ),
        findings=findings,
    )
