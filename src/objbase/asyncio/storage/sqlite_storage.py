from objbase.asyncio.storage.threaded_storage import ThreadedAsyncStorage
from objbase.storage.sqlite_storage import SQLiteStorage


class AsyncSQLiteStorage(ThreadedAsyncStorage[SQLiteStorage]):
    """Async counterpart of ``SQLiteStorage``, using the same data layout.

    Uses the standard library ``sqlite3`` module, so it needs no extra dependencies.
    Each call runs in a worker thread (``asyncio.to_thread``) with its own connection,
    so the event loop is never blocked by database I/O.
    """

    def __init__(self, db_path: str):
        # Creates the table if needed; this one-off setup runs synchronously.
        super().__init__(SQLiteStorage(db_path))

    @property
    def db_path(self) -> str:
        return self.sync_storage.db_path
