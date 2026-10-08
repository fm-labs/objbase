from typing import Any

from objbase.errors import CollectionError, ItemNotFoundError
from objbase.interface import Item, Storage


def require_item_id(item: Item) -> Any:
    """Return the item's id, raising ``ValueError`` if it is missing or empty."""
    _id = item.get("id")
    if not _id:
        raise ValueError("Item id is required.")
    return _id


def check_patch_data(id: str, data: Item) -> None:
    """Raise ``ValueError`` if patch data would change the item id."""
    if "id" in data and data["id"] != id:
        raise ValueError("Patch data must not change the item id.")


def require_read_back(item: Item | None, item_type: str, id: str) -> Item:
    """Return an item read back after a successful write, raising if it vanished."""
    if item is None:
        raise CollectionError(f"Item '{id}' of type '{item_type}' could not be read back after writing.")
    return item


class Collection:
    
    def __init__(self, item_type: str, storage: Storage):
        self.storage = storage
        self.item_type = item_type

    def keys(self) -> list[str]:
        return self.storage.keys(self.item_type)

    def items(self) -> list[Item]:
        return self.storage.items(self.item_type)

    def get(self, id: str) -> Item | None:
        return self.storage.read(self.item_type, id)

    def save(self, item: Item) -> Item:
        _id = require_item_id(item)
        if not self.storage.write(self.item_type, item):
            raise CollectionError(f"Failed to save item '{_id}'.")
        return require_read_back(self.storage.read(self.item_type, _id), self.item_type, _id)

    def patch(self, id: str, data: Item) -> Item:
        check_patch_data(id, data)
        item = self.storage.read(self.item_type, id)
        if item is None:
            raise ItemNotFoundError(self.item_type, id)
        item.update(data)
        if not self.storage.write(self.item_type, item):
            raise CollectionError(f"Failed to patch item '{id}'.")
        return require_read_back(self.storage.read(self.item_type, id), self.item_type, id)

    def delete(self, id: str) -> bool:
        return self.storage.delete(self.item_type, id)
