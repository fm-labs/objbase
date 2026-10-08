from objbase.errors import CollectionError, ItemNotFoundError
from objbase.interface import AsyncStorage, Item
from objbase.collection import check_patch_data, require_item_id, require_read_back


class AsyncCollection:
    """Async counterpart of ``Collection``, backed by an ``AsyncStorage``.

    Same methods and behaviour as ``Collection``, but every method is a coroutine.
    """

    def __init__(self, item_type: str, storage: AsyncStorage):
        if not isinstance(storage, AsyncStorage):
            raise TypeError(
                f"{type(storage).__name__} is not an AsyncStorage; use Collection for sync storage adapters."
            )
        self.storage = storage
        self.item_type = item_type

    async def keys(self) -> list[str]:
        return await self.storage.akeys(self.item_type)

    async def filter(self) -> list[Item]:
        return await self.storage.aitems(self.item_type)

    async def get(self, id: str) -> Item | None:
        return await self.storage.aread(self.item_type, id)

    async def save(self, item: Item) -> Item:
        _id = require_item_id(item)
        if not await self.storage.awrite(self.item_type, item):
            raise CollectionError(f"Failed to save item '{_id}'.")
        return require_read_back(await self.storage.aread(self.item_type, _id), self.item_type, _id)

    async def patch(self, id: str, data: Item) -> Item:
        check_patch_data(id, data)
        item = await self.storage.aread(self.item_type, id)
        if item is None:
            raise ItemNotFoundError(self.item_type, id)
        item.update(data)
        if not await self.storage.awrite(self.item_type, item):
            raise CollectionError(f"Failed to patch item '{id}'.")
        return require_read_back(await self.storage.aread(self.item_type, id), self.item_type, id)

    async def delete(self, id: str) -> bool:
        return await self.storage.adelete(self.item_type, id)
