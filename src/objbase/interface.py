from typing import Any, Protocol, runtime_checkable

Item = dict[str, Any]
"""A stored item: a JSON-serializable dict with an ``"id"`` key."""


@runtime_checkable
class Storage(Protocol):
    """Storage contract shared by all adapters.

    - ``keys`` returns all item ids of a type, or ``[]`` if there are none.
    - ``items`` returns all items of a type, or ``[]`` if there are none.
    - ``read`` returns the item, or ``None`` if it does not exist.
    - ``write`` inserts the item or replaces an existing item with the same id entirely.
    - ``delete`` returns ``True`` if an item was removed, ``False`` if it did not exist.
    - Returned items are independent copies; mutating them does not change stored data.
    """

    def keys(self, item_type: str) -> list[str]: ...

    def items(self, item_type: str) -> list[Item]: ...

    def read(self, item_type: str, id: str) -> Item | None: ...

    def write(self, item_type: str, item: Item) -> bool: ...

    def delete(self, item_type: str, id: str) -> bool: ...


@runtime_checkable
class AsyncStorage(Protocol):
    """Async counterpart of ``Storage``, with the same contract."""

    async def akeys(self, item_type: str) -> list[str]: ...

    async def aitems(self, item_type: str) -> list[Item]: ...

    async def aread(self, item_type: str, id: str) -> Item | None: ...

    async def awrite(self, item_type: str, item: Item) -> bool: ...

    async def adelete(self, item_type: str, id: str) -> bool: ...
