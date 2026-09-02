"""SDMX-specific application exceptions."""


class SDMXError(Exception):
    """Base exception for SDMX operations."""


class SDMXProviderError(SDMXError):
    """The remote provider failed or returned an unusable response."""


class SDMXStructureNotFound(SDMXProviderError):
    """The requested structure does not exist at the provider."""


class SDMXParseError(SDMXError):
    """An SDMX structure response could not be parsed."""
