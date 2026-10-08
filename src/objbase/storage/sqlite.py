import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from objbase.interface import Item, Storage

CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS items (
        item_type  TEXT NOT NULL,
        id              TEXT NOT NULL,
        data            TEXT NOT NULL,
        PRIMARY KEY (item_type, id)
    )
"""


class SQLiteStorage(Storage):
    """SQLite-backed storage. Each item is stored as a JSON blob in a single table."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        with self._connect() as conn:
            conn.execute(CREATE_TABLE_SQL)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit on success (rollback on error), and always close it."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def keys(self, item_type: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM items WHERE item_type = ?",
                (item_type,),
            ).fetchall()
        return [row["id"] for row in rows]

    def items(self, item_type: str) -> list[Item]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data FROM items WHERE item_type = ?",
                (item_type,),
            ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def read(self, item_type: str, id: str) -> Item | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM items WHERE item_type = ? AND id = ?",
                (item_type, id),
            ).fetchone()
        return json.loads(row["data"]) if row else None

    def write(self, item_type: str, item: Item) -> bool:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO items (item_type, id, data)
                VALUES (?, ?, ?)
                ON CONFLICT (item_type, id) DO UPDATE SET data = excluded.data
                """,
                (item_type, item["id"], json.dumps(item)),
            )
        return True

    def delete(self, item_type: str, id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM items WHERE item_type = ? AND id = ?",
                (item_type, id),
            )
        return cursor.rowcount > 0
