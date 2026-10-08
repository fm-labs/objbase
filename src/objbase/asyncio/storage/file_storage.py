import asyncio

from objbase.asyncio.storage.threaded_storage import ThreadedAsyncStorage
from objbase.storage.file_storage import DirectoryBasedStorage, FileBasedStorage


class AsyncFileBasedStorage(ThreadedAsyncStorage[FileBasedStorage]):
    """Async counterpart of ``FileBasedStorage``, using the same files and locks.

    Each call runs in a worker thread (``asyncio.to_thread``), so the event loop is never
    blocked by file I/O or while waiting for a file lock. Sync and async adapters on the
    same directory can be used side by side, in one or several processes.
    """

    def __init__(self, base_dir: str):
        super().__init__(FileBasedStorage(base_dir))

    @property
    def inventory_dir(self) -> str:
        return self.sync_storage.inventory_dir


class AsyncDirectoryBasedStorage(ThreadedAsyncStorage[DirectoryBasedStorage]):
    """Async counterpart of ``DirectoryBasedStorage``, using the same files, index and locks.

    Each call runs in a worker thread (``asyncio.to_thread``), so the event loop is never
    blocked by file I/O or while waiting for a file lock. Sync and async adapters on the
    same directory can be used side by side, in one or several processes.
    """

    def __init__(self, base_dir: str):
        super().__init__(DirectoryBasedStorage(base_dir))

    @property
    def inventory_dir(self) -> str:
        return self.sync_storage.inventory_dir

    async def arebuild_index(self, item_type: str) -> None:
        """Async counterpart of ``DirectoryBasedStorage.rebuild_index``."""
        await asyncio.to_thread(self.sync_storage.rebuild_index, item_type)
