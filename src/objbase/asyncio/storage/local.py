import asyncio

from objbase.asyncio.storage.threaded import ThreadedAsyncStorage
from objbase.storage.local import LocalDirectoryStorage, LocalFileStorage


class AsyncLocalFileStorage(ThreadedAsyncStorage[LocalFileStorage]):
    """Async counterpart of ``LocalFileStorage``, using the same files and locks.

    Each call runs in a worker thread (``asyncio.to_thread``), so the event loop is never
    blocked by file I/O or while waiting for a file lock. Sync and async adapters on the
    same directory can be used side by side, in one or several processes.
    """

    def __init__(self, base_dir: str):
        super().__init__(LocalFileStorage(base_dir))

    @property
    def inventory_dir(self) -> str:
        return self.sync_storage.inventory_dir


class AsyncLocalDirectoryStorage(ThreadedAsyncStorage[LocalDirectoryStorage]):
    """Async counterpart of ``LocalDirectoryStorage``, using the same files, index and locks.

    Each call runs in a worker thread (``asyncio.to_thread``), so the event loop is never
    blocked by file I/O or while waiting for a file lock. Sync and async adapters on the
    same directory can be used side by side, in one or several processes.
    """

    def __init__(self, base_dir: str):
        super().__init__(LocalDirectoryStorage(base_dir))

    @property
    def inventory_dir(self) -> str:
        return self.sync_storage.inventory_dir

    async def arebuild_index(self, item_type: str) -> None:
        """Async counterpart of ``LocalDirectoryStorage.rebuild_index``."""
        await asyncio.to_thread(self.sync_storage.rebuild_index, item_type)
