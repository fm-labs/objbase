import copy

from objbase.interface import AsyncStorage, Item, Storage


class InMemoryStorage(Storage, AsyncStorage):
    """In-memory storage implementation for inventory items.

    Items are deep-copied on the way in and out, so callers never share
    mutable state with the store.
    """

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Item]] = {}

    def keys(self, item_type: str) -> list[str]:
        return list(self.data.get(item_type, {}))

    def items(self, item_type: str) -> list[Item]:
        return copy.deepcopy(list(self.data.get(item_type, {}).values()))

    def read(self, item_type: str, id: str) -> Item | None:
        return copy.deepcopy(self.data.get(item_type, {}).get(id))

    def write(self, item_type: str, item: Item) -> bool:
        if item_type not in self.data:
            self.data[item_type] = {}
        self.data[item_type][item["id"]] = copy.deepcopy(item)
        return True

    def delete(self, item_type: str, id: str) -> bool:
        if item_type in self.data and id in self.data[item_type]:
            del self.data[item_type][id]
            return True
        return False

    async def akeys(self, item_type: str) -> list[str]:
        return self.keys(item_type)

    async def aitems(self, item_type: str) -> list[Item]:
        return self.items(item_type)

    async def aread(self, item_type: str, id: str) -> Item | None:
        return self.read(item_type, id)

    async def awrite(self, item_type: str, item: Item) -> bool:
        return self.write(item_type, item)

    async def adelete(self, item_type: str, id: str) -> bool:
        return self.delete(item_type, id)
