import inspect
import logging
from typing import Any

from objbase.actions import ActionHandler, ActionParams, check_action_name, check_action_result
from objbase.errors import ActionNotFoundError, CollectionError, ItemNotFoundError
from objbase.interface import Item, Storage

logger = logging.getLogger(__name__)


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
        self.actions: dict[str, ActionHandler] = {}

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

    def register_action(self, name: str, handler: ActionHandler) -> None:
        """Register ``handler`` as action ``name``, replacing any handler already registered under that name."""
        check_action_name(name)
        if inspect.iscoroutinefunction(handler):
            raise TypeError(f"Action '{name}' has an async handler; register it on an AsyncCollection instead.")
        self.actions[name] = handler

    def run_action(self, id: str, name: str, params: ActionParams | None = None) -> Item:
        """Run action ``name`` on item ``id`` and return the resulting item.

        If the handler returns an item, it is saved (replacing the stored item) and
        returned; if it returns ``None``, the stored item is returned unchanged.
        """
        handler = self.actions.get(name)
        if handler is None:
            raise ActionNotFoundError(name, f"item type '{self.item_type}'")
        item = self.storage.read(self.item_type, id)
        if item is None:
            raise ItemNotFoundError(self.item_type, id)
        logger.debug("Running action %r on %s item %r", name, self.item_type, id)
        result = handler(item, params or {})
        if result is None:
            logger.debug("Action %r on %s item %r left the item unchanged", name, self.item_type, id)
            return item
        check_action_result(id, result)
        logger.debug("Action %r on %s item %r returned an updated item; saving", name, self.item_type, id)
        return self.save(result)
