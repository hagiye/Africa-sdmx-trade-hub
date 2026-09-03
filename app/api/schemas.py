"""Public response schemas for the read-only metadata API."""

from pydantic import BaseModel, Field


class StructureIdentity(BaseModel):
    agency: str
    id: str
    version: str
    name: str
    labels: dict[str, str] = Field(default_factory=dict)


class DataflowResponse(StructureIdentity):
    description: str | None = None
    dsd: dict[str, str] | None = None


class ComponentResponse(BaseModel):
    concept: str
    role: str | None = None
    position: int | None = None
    attachment_level: str | None = None
    representation: str | None = None
    codelist: dict[str, str] | None = None


class DSDResponse(StructureIdentity):
    dimensions: list[ComponentResponse]
    attributes: list[ComponentResponse]
    measures: list[ComponentResponse]


class CodelistResponse(StructureIdentity):
    code_count: int


class CodeResponse(BaseModel):
    code: str
    parent_code: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class CodePage(BaseModel):
    items: list[CodeResponse]
    page: int
    page_size: int
    total: int
    pages: int


class AfrTradeObservationResponse(BaseModel):
    id: int
    FREQ: str
    REF_AREA: str
    COUNTERPART_AREA: str
    TRADE_FLOW: str
    PRODUCT_SCHEME: str
    PRODUCT: str
    UNIT_MEASURE: str
    TIME_PERIOD: str
    OBS_VALUE: str
    OBS_STATUS: str | None = None
    CONF_STATUS: str | None = None
    UNIT_MULT: str
    DECIMALS: int | None = None
    SOURCE: str
    target_key_hash: str
    mapping_definition_id: str
    mapping_version: str


class AfrTradeObservationPage(BaseModel):
    items: list[AfrTradeObservationResponse]
    total: int
    limit: int
    offset: int


class AfrTradeMetadataResponse(BaseModel):
    agency: str
    dataflow: str
    version: str
    DSD: dict[str, str]
    dimensions: list[str]
    attributes: list[str]
    components: list[dict[str, object]]
    codelists: list[dict[str, object]]
    disclaimer: str
