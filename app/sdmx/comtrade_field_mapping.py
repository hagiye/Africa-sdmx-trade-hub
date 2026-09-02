"""Declarative UN Comtrade JSON-to-SDMX metadata.

This module deliberately contains no observation parsing or normalization.
"""

from __future__ import annotations


DSD_DIMENSIONS = (
    "FREQ",
    "REF_AREA",
    "TRADE_FLOW",
    "COMMODITY_1",
    "COMMODITY_1_CONF",
    "COMMODITY_2",
    "COMMODITY_2_CONF",
    "COMMODITY_CUSTOM_BREAKDOWN",
    "COUNTERPART_AREA_1",
    "COUNTERPART_AREA_1_CONF",
    "COUNTERPART_AREA_2",
    "COUNTERPART_AREA_2_CONF",
    "TRANSPORT_MODE_BORDER",
    "TRANSPORT_MODE_BORDER_CONF",
    "CUSTOMS_PROC",
    "ACTIVITY",
    "TRANSFORMATION",
    "MEASURE",
    "TIME_PERIOD",
)

DSD_ATTRIBUTES = (
    "UNIT_MULT",
    "UNIT_MEASURE",
    "COMMENT_OBS",
    "TRADE_SYSTEM",
    "COMMODITY_CUSTOM_CODE",
    "COMMODITY_CUSTOM_DESC",
    "COUNTERPART_AREA_1_TYPE",
    "COUNTERPART_AREA_2_TYPE",
    "COUNTERPART_AREA_1_ANNOTATION",
    "COUNTERPART_AREA_2_ANNOTATION",
    "OBS_STATUS",
)

DSD_MEASURES = ("OBS_VALUE",)
REAL_DSD_CONCEPTS = frozenset(DSD_DIMENSIONS + DSD_ATTRIBUTES + DSD_MEASURES)


def _field(
    meaning: str,
    concept: str | None,
    relationship: str,
    confidence: str,
    notes: str,
) -> dict[str, str | None]:
    return {
        "meaning": meaning,
        "concept": concept,
        "relationship": relationship,
        "confidence": confidence,
        "notes": notes,
    }


# Every key below was observed in all three controlled real records. ``DIRECT``
# means the field expresses the SDMX concept without reshaping; ``DERIVED`` means
# translation or combination is required; ``UNKNOWN`` avoids inventing a link.
COMTRADE_JSON_TO_SDMX = {
    "aggrLevel": _field("Commodity aggregation level", None, "UNKNOWN", "UNKNOWN", "No matching IMTS 1.2 concept was established."),
    "altQty": _field("Alternative quantity", "OBS_VALUE", "DERIVED", "HIGH", "Would require a corresponding MEASURE and unit when reshaped to SDMX."),
    "altQtyUnitAbbr": _field("Alternative quantity unit abbreviation", "UNIT_MEASURE", "DERIVED", "HIGH", "Provider unit label; an SDMX unit code translation is required."),
    "altQtyUnitCode": _field("Alternative quantity unit code", "UNIT_MEASURE", "DERIVED", "HIGH", "Provider code; not assumed to equal the SDMX codelist code."),
    "cifvalue": _field("CIF trade value", "OBS_VALUE", "DERIVED", "HIGH", "Numeric value for a CIF-value measure; MEASURE is not explicitly returned."),
    "classificationCode": _field("Commodity classification edition", "COMMODITY_1", "DERIVED", "CONFIRMED", "Combined with cmdCode to resolve the SDMX commodity code."),
    "classificationSearchCode": _field("Commodity classification search edition", "COMMODITY_1", "DERIVED", "HIGH", "Provider search metadata; observed equal to classificationCode."),
    "cmdCode": _field("Commodity code", "COMMODITY_1", "DERIVED", "CONFIRMED", "Combined with classificationCode; S4 + TOTAL corresponds to SITC4_TOTAL."),
    "cmdDesc": _field("Commodity description", "COMMODITY_1", "DERIVED", "HIGH", "English label, not an SDMX code."),
    "customsCode": _field("Customs procedure code", "CUSTOMS_PROC", "DERIVED", "HIGH", "Provider code must be checked against the SDMX codelist before normalization."),
    "customsDesc": _field("Customs procedure description", "CUSTOMS_PROC", "DERIVED", "HIGH", "Provider label for customsCode."),
    "flowCode": _field("Trade flow code", "TRADE_FLOW", "DIRECT", "CONFIRMED", "The selected stored DSD code M produced this record."),
    "flowDesc": _field("Trade flow description", "TRADE_FLOW", "DIRECT", "HIGH", "Provider label for flowCode."),
    "fobvalue": _field("FOB trade value", "OBS_VALUE", "DERIVED", "HIGH", "Numeric value for an FOB-value measure; null in all inspected records."),
    "freqCode": _field("Frequency code", "FREQ", "DIRECT", "CONFIRMED", "A is the selected annual SDMX frequency code."),
    "grossWgt": _field("Gross weight", "OBS_VALUE", "DERIVED", "HIGH", "Numeric value for a gross-weight measure; MEASURE is not explicitly returned."),
    "isAggregate": _field("Aggregate-record indicator", None, "UNKNOWN", "UNKNOWN", "Provider metadata; no direct DSD concept established."),
    "isAltQtyEstimated": _field("Alternative quantity estimated indicator", "OBS_STATUS", "UNKNOWN", "UNKNOWN", "May be quality/status metadata, but no OBS_STATUS code mapping is evidenced."),
    "isGrossWgtEstimated": _field("Gross weight estimated indicator", "OBS_STATUS", "UNKNOWN", "UNKNOWN", "May be quality/status metadata, but no OBS_STATUS code mapping is evidenced."),
    "isLeaf": _field("Commodity hierarchy leaf indicator", None, "UNKNOWN", "UNKNOWN", "Provider hierarchy metadata; no direct DSD concept established."),
    "isNetWgtEstimated": _field("Net weight estimated indicator", "OBS_STATUS", "UNKNOWN", "UNKNOWN", "May be quality/status metadata, but no OBS_STATUS code mapping is evidenced."),
    "isOriginalClassification": _field("Original-classification indicator", None, "UNKNOWN", "UNKNOWN", "Provider classification metadata; no direct DSD concept established."),
    "isQtyEstimated": _field("Quantity estimated indicator", "OBS_STATUS", "UNKNOWN", "UNKNOWN", "May be quality/status metadata, but no OBS_STATUS code mapping is evidenced."),
    "isReported": _field("Reported-versus-derived indicator", "OBS_STATUS", "UNKNOWN", "UNKNOWN", "May be quality/status metadata, but no OBS_STATUS code mapping is evidenced."),
    "legacyEstimationFlag": _field("Legacy estimation flag", "OBS_STATUS", "UNKNOWN", "UNKNOWN", "Provider legacy flag semantics are not proven equivalent to OBS_STATUS."),
    "mosCode": _field("Mode-of-supply code", None, "UNKNOWN", "UNKNOWN", "Meaning in this merchandise response is not established from the fixture or DSD."),
    "motCode": _field("Mode-of-transport code", "TRANSPORT_MODE_BORDER", "DERIVED", "HIGH", "Provider code must be translated or verified against the DSD codelist."),
    "motDesc": _field("Mode-of-transport description", "TRANSPORT_MODE_BORDER", "DERIVED", "HIGH", "Provider label for motCode."),
    "netWgt": _field("Net weight", "OBS_VALUE", "DERIVED", "HIGH", "Numeric value for a net-weight measure; MEASURE is not explicitly returned."),
    "partner2Code": _field("Second counterpart provider code", "COUNTERPART_AREA_2", "DERIVED", "CONFIRMED", "Official translation maps provider 0 (World aggregate) to stored SDMX W0."),
    "partner2Desc": _field("Second counterpart label", "COUNTERPART_AREA_2", "DERIVED", "HIGH", "World is an aggregate area, not a country."),
    "partner2ISO": _field("Second counterpart provider ISO-like code", "COUNTERPART_AREA_2", "DERIVED", "HIGH", "W00 is provider notation; the stored SDMX code is W0."),
    "partnerCode": _field("First counterpart provider code", "COUNTERPART_AREA_1", "DERIVED", "CONFIRMED", "Official translation maps provider 0 (World aggregate) to stored SDMX W0."),
    "partnerDesc": _field("First counterpart label", "COUNTERPART_AREA_1", "DERIVED", "HIGH", "World is an aggregate area, not a country."),
    "partnerISO": _field("First counterpart provider ISO-like code", "COUNTERPART_AREA_1", "DERIVED", "HIGH", "W00 is provider notation; the stored SDMX code is W0."),
    "period": _field("Observation period", "TIME_PERIOD", "DIRECT", "CONFIRMED", "Annual period is represented as YYYY."),
    "primaryValue": _field("Provider-selected primary numeric value", "OBS_VALUE", "DIRECT", "HIGH", "Observation value, not the MEASURE dimension; equals cifvalue in these import records."),
    "qty": _field("Quantity", "OBS_VALUE", "DERIVED", "HIGH", "Numeric value for a quantity measure; MEASURE and unit are separate SDMX semantics."),
    "qtyUnitAbbr": _field("Quantity unit abbreviation", "UNIT_MEASURE", "DERIVED", "HIGH", "Provider unit label; an SDMX unit code translation is required."),
    "qtyUnitCode": _field("Quantity unit code", "UNIT_MEASURE", "DERIVED", "HIGH", "Provider code; not assumed to equal the SDMX codelist code."),
    "refMonth": _field("Provider reference-month marker", "TIME_PERIOD", "DERIVED", "MEDIUM", "52 accompanies annual records; period is the direct time field."),
    "refPeriodId": _field("Provider reference-period identifier", "TIME_PERIOD", "DERIVED", "HIGH", "YYYY0101 identifier from which the annual period can be derived."),
    "refYear": _field("Reference year", "TIME_PERIOD", "DERIVED", "HIGH", "Numeric year equivalent to period in these annual records."),
    "reporterCode": _field("Reporter M49 provider code", "REF_AREA", "DERIVED", "CONFIRMED", "Official provider reference translation maps 788 to stored SDMX TN."),
    "reporterDesc": _field("Reporter label", "REF_AREA", "DERIVED", "HIGH", "English area label, not the SDMX area code."),
    "reporterISO": _field("Reporter ISO alpha-3 code", "REF_AREA", "DERIVED", "HIGH", "TUN identifies Tunisia; the stored SDMX code is TN."),
    "typeCode": _field("Comtrade trade-data type", None, "UNKNOWN", "UNKNOWN", "C identifies commodity trade in the API route; no DSD dimension mapping established."),
}

UNMAPPED_COMTRADE_FIELDS = frozenset(
    name
    for name, metadata in COMTRADE_JSON_TO_SDMX.items()
    if metadata["concept"] is None or metadata["relationship"] == "UNKNOWN"
)

# DSD dimensions not represented by a dedicated field in the simplified JSON
# records. MEASURE is especially important: measure-specific numeric columns do
# not themselves expose the SDMX measure-dimension code.
NOT_EXPOSED_DSD_DIMENSIONS = frozenset(
    {
        "COMMODITY_1_CONF",
        "COMMODITY_2",
        "COMMODITY_2_CONF",
        "COMMODITY_CUSTOM_BREAKDOWN",
        "COUNTERPART_AREA_1_CONF",
        "COUNTERPART_AREA_2_CONF",
        "TRANSPORT_MODE_BORDER_CONF",
        "ACTIVITY",
        "TRANSFORMATION",
        "MEASURE",
    }
)

WORLD_PARTNER_CLASSIFICATION = {
    "provider_code": 0,
    "provider_label": "World",
    "provider_iso": "W00",
    "sdmx_code": "W0",
    "area_type": "AGGREGATE",
    "is_country": False,
}
