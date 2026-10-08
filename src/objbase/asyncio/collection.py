import asyncio
import inspect
import logging
from typing import cast

from objbase.actions import (
    ActionHandler,
    ActionParams,
    AsyncActionHandler,
    check_action_name,
    check_action_result,
)
from objbase.collection import check_patch_data, require_item_id, require_read_back
from objbase.errors import ActionNotFoundError, CollectionError, ItemNotFoundError
from objbase.interface import AsyncStorage, Item

logger = logging.getLogger(__name__)


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
        self.actions: dict[str, ActionHandler | AsyncActionHandler] = {}

    async def keys(self) -> list[str]:
        return await self.storage.akeys(self.item_type)

    async def items(self) -> list[Item]:
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

    def register_action(self, name: str, handler: ActionHandler | AsyncActionHandler) -> None:
        """Register ``handler`` as action ``name``, replacing any handler already registered under that name.

        Async handlers are awaited; sync handlers run in a worker thread (``asyncio.to_thread``).
        """
        check_action_name(name)
        self.actions[name] = handler

    async def run_action(self, id: str, name: str, params: ActionParams | None = None) -> Item:
        """Run action ``name`` on item ``id`` and return the resulting item.

        If the handler returns an item, it is saved (replacing the stored item) and
        returned; if it returns ``None``, the stored item is returned unchanged.
        """
        handler = self.actions.get(name)
        if handler is None:
            raise ActionNotFoundError(name, f"item type '{self.item_type}'")
        item = await self.storage.aread(self.item_type, id)
        if item is None:
            raise ItemNotFoundError(self.item_type, id)
        logger.debug("Running action %r on %s item %r", name, self.item_type, id)
        if inspect.iscoroutinefunction(handler):
            result = await cast(AsyncActionHandler, handler)(item, params or {})
        else:
            result = await asyncio.to_thread(cast(ActionHandler, handler), item, params or {})
        if result is None:
            logger.debug("Action %r on %s item %r left the item unchanged", name, self.item_type, id)
            return item
        check_action_result(id, result)
        logger.debug("Action %r on %s item %r returned an updated item; saving", name, self.item_type, id)
        return await self.save(result)
