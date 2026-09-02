"""Higher-level SDMX structure discovery operations."""

from app.sdmx.client import SDMXClient, SDMXResponse
from app.sdmx.models import Codelist, ConceptScheme, Dataflow, DataStructure, StructureRef
from app.sdmx.parser import (
    parse_codelists,
    parse_concept_schemes,
    parse_constraints,
    parse_dataflows,
    parse_dsd,
)

PROVIDER_NAME = "IMF SDMX Central"
PROVIDER_BASE_URL = "https://sdmxcentral.imf.org/sdmx/v2/"
TRADE_DATAFLOW = StructureRef("dataflow", "UNSD", "IMTS_A", "1.0")
TRADE_DSD = StructureRef("datastructure", "UNSD", "IMTS", "1.2")


class SDMXDiscovery:
    def __init__(self, client: SDMXClient) -> None:
        self.client = client

    def get_dataflows(
        self, agency: str = "all", structure_id: str = "all", version: str = "latest"
    ) -> tuple[list[Dataflow], SDMXResponse]:
        response = self.client.get_structure("dataflow", agency, structure_id, version)
        return parse_dataflows(response.content), response

    def get_dsd(self, ref: StructureRef) -> tuple[DataStructure, SDMXResponse]:
        response = self.client.get_structure(
            "datastructure", ref.agency, ref.structure_id, ref.version
        )
        return parse_dsd(response.content), response

    def get_concept_scheme(
        self, ref: StructureRef
    ) -> tuple[ConceptScheme, SDMXResponse]:
        response = self.client.get_structure(
            "conceptscheme", ref.agency, ref.structure_id, ref.version
        )
        structures = parse_concept_schemes(response.content)
        if not structures:
            raise ValueError(f"Provider returned no concept scheme for {ref}")
        return structures[0], response

    def get_codelist(self, ref: StructureRef) -> tuple[Codelist, SDMXResponse]:
        response = self.client.get_structure(
            "codelist", ref.agency, ref.structure_id, ref.version
        )
        structures = parse_codelists(response.content)
        if not structures:
            raise ValueError(f"Provider returned no codelist for {ref}")
        return structures[0], response

    def get_constraints(
        self, agency: str, structure_id: str = "all", version: str = "latest"
    ) -> tuple[list[StructureRef], SDMXResponse]:
        response = self.client.get_structure(
            "dataconstraint", agency, structure_id, version
        )
        return parse_constraints(response.content), response
