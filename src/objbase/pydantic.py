import pydantic

from objbase.asyncio.collection import AsyncCollection
from objbase.collection import Collection, check_patch_data
from objbase.errors import ItemNotFoundError
from objbase.interface import AsyncStorage, Item, Storage


def _dump(model: pydantic.BaseModel) -> Item:
    """Convert a model to the JSON-compatible dict that is stored."""
    return model.model_dump(mode="json")


def _validated[M: pydantic.BaseModel](model_class: type[M], data: Item | M) -> Item:
    """Validate ``data`` against ``model_class`` and return the dict to store.

    Runs before every write, so invalid data raises ``ValidationError`` without
    being stored. This also catches models made invalid after construction
    (Pydantic does not validate attribute assignment by default).
    """
    # dict(model) takes the raw field values, so a model with invalid values is
    # re-validated (and rejected) rather than serialized as-is.
    raw = dict(data) if isinstance(data, pydantic.BaseModel) else data
    return _dump(model_class.model_validate(raw))


def _patched[M: pydantic.BaseModel](
    model_class: type[M], item_type: str, id: str, current: Item | None, data: Item | M
) -> Item:
    """Merge patch ``data`` into the ``current`` stored item and validate the result."""
    patch = dict(data) if isinstance(data, pydantic.BaseModel) else data
    check_patch_data(id, patch)
    if current is None:
        raise ItemNotFoundError(item_type, id)
    return _validated(model_class, {**current, **patch})


class PydanticCollection[M: pydantic.BaseModel]:
    """Collection that validates items against a Pydantic model.

    Wraps an ``Collection``: items are stored as plain dicts and returned as
    ``model_class`` instances. The model type is inferred from ``model_class``,
    so ``PydanticCollection("todo", storage, Todo).get("1")`` is typed ``Todo | None``.

    ``save`` and ``patch`` validate the complete item before writing it, so data
    that fails validation raises ``pydantic.ValidationError`` and is never stored.
    """

    def __init__(self, item_type: str, storage: Storage, model_class: type[M]):
        self.model_class = model_class
        self.inventory = Collection(item_type, storage)

    @property
    def item_type(self) -> str:
        return self.inventory.item_type

    @property
    def storage(self) -> Storage:
        return self.inventory.storage

    def keys(self) -> list[str]:
        return self.inventory.keys()

    def filter(self) -> list[M]:
        return [self.model_class.model_validate(item) for item in self.inventory.items()]

    def save(self, model: M) -> M:
        return self.model_class.model_validate(self.inventory.save(_validated(self.model_class, model)))

    def get(self, id: str) -> M | None:
        item = self.inventory.get(id)
        if item is None:
            return None
        return self.model_class.model_validate(item)

    def patch(self, id: str, data: Item | M) -> M:
        item = _patched(self.model_class, self.item_type, id, self.inventory.get(id), data)
        return self.model_class.model_validate(self.inventory.save(item))

    def delete(self, id: str) -> bool:
        return self.inventory.delete(id)


class AsyncPydanticCollection[M: pydantic.BaseModel]:
    """Async counterpart of ``PydanticCollection``, backed by an ``AsyncStorage``.

    Same methods and behaviour as ``PydanticCollection``, but every method is a coroutine.
    """

    def __init__(self, item_type: str, storage: AsyncStorage, model_class: type[M]):
        self.model_class = model_class
        self.inventory = AsyncCollection(item_type, storage)

    @property
    def item_type(self) -> str:
        return self.inventory.item_type

    @property
    def storage(self) -> AsyncStorage:
        return self.inventory.storage

    async def keys(self) -> list[str]:
        return await self.inventory.keys()

    async def filter(self) -> list[M]:
        return [self.model_class.model_validate(item) for item in await self.inventory.items()]

    async def save(self, model: M) -> M:
        return self.model_class.model_validate(await self.inventory.save(_validated(self.model_class, model)))

    async def get(self, id: str) -> M | None:
        item = await self.inventory.get(id)
        if item is None:
            return None
        return self.model_class.model_validate(item)

    async def patch(self, id: str, data: Item | M) -> M:
        item = _patched(self.model_class, self.item_type, id, await self.inventory.get(id), data)
        return self.model_class.model_validate(await self.inventory.save(item))

    async def delete(self, id: str) -> bool:
        return await self.inventory.delete(id)
