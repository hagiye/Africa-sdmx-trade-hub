"""Verify that the configured PostgreSQL database accepts connections."""

from sqlalchemy import text

from app.database.session import engine


def main() -> None:
    """Print the PostgreSQL server version."""
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version()"))
        print(version.scalar_one())


if __name__ == "__main__":
    main()
