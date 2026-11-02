import sqlite3
from contextlib import contextmanager
from pathlib import Path

from prs.errors import ValidationError


class Database:
    """One connection per operation; atomic writes and enforced foreign keys."""

    def __init__(self, path: str):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=1.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        """Initialize only a fresh or Version 2 database; never migrate V1 in place."""
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            has_tables = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
            ).fetchone()
            if has_tables and version != 2:
                raise ValidationError(
                    "This is not a Version 2 database. Choose a new database file; "
                    "Version 1 data must remain separate."
                )
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")
            )
            db.execute("PRAGMA user_version = 2")
