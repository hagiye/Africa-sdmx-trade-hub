"""Confirm that sdmx1 is installed and its known sources are available."""

import sdmx


def main() -> None:
    """Print the sdmx1 version and known source identifiers."""
    print(f"sdmx1 version: {sdmx.__version__}")
    sources = sdmx.list_sources()
    print(f"Known SDMX sources ({len(sources)}):")
    print(", ".join(sources))


if __name__ == "__main__":
    main()
