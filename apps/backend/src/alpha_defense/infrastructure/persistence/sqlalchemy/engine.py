"""SQLite engine construction without implicit schema mutation."""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

import sqlalchemy as sa
from sqlalchemy.engine import Engine


def create_sqlite_engine(database_path: Path, *, echo: bool = False) -> Engine:
    if not isinstance(database_path, Path):
        raise TypeError("database_path must be a pathlib.Path")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = sa.create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 5.0},
        echo=echo,
    )

    @sa.event.listens_for(engine, "connect")
    def _configure_sqlite(connection: SQLiteConnection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine
