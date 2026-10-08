import asyncio

from objbase.interface import AsyncStorage, Item, Storage


class ThreadedAsyncStorage[S: Storage](AsyncStorage):
    """Base for async adapters that run a blocking sync adapter in worker threads.

    Each call is passed to ``asyncio.to_thread``, so the event loop is never blocked by
    I/O. The sync adapter must be safe to call from several threads at once.
    """

    def __init__(self, sync_storage: S):
        self.sync_storage = sync_storage

    async def akeys(self, item_type: str) -> list[str]:
        return await asyncio.to_thread(self.sync_storage.keys, item_type)

    async def aitems(self, item_type: str) -> list[Item]:
        return await asyncio.to_thread(self.sync_storage.items, item_type)

    async def aread(self, item_type: str, id: str) -> Item | None:
        return await asyncio.to_thread(self.sync_storage.read, item_type, id)

    async def awrite(self, item_type: str, item: Item) -> bool:
        return await asyncio.to_thread(self.sync_storage.write, item_type, item)

    async def adelete(self, item_type: str, id: str) -> bool:
        return await asyncio.to_thread(self.sync_storage.delete, item_type, id)
