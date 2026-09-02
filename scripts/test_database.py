"""Verify that the configured PostgreSQL database accepts connections."""

import sys
from pathlib import Path

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.session import engine


def main() -> None:
    """Print the PostgreSQL server version."""
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version()"))
        print(version.scalar_one())


if __name__ == "__main__":
    main()
