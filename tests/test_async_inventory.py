"""Tests for the AsyncInventory and AsyncPydanticInventory APIs."""

import pydantic
import pytest

from objbase.asyncio.inventory import AsyncInventory
from objbase.errors import InventoryError, ItemNotFoundError
from objbase.pydantic import AsyncPydanticInventory
from objbase.storage.inmemory import InMemoryStorage
from objbase.storage.sqlite import SQLiteStorage


@pytest.fixture()
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture()
def todos(storage) -> AsyncInventory:
    return AsyncInventory(item_type="todo", storage=storage)


class FailingStorage(InMemoryStorage):
    async def awrite(self, item_type, item):
        return False


class TestAsyncInventoryInit:
    def test_rejects_sync_only_storage(self, tmp_path):
        with pytest.raises(TypeError, match="not an AsyncStorage"):
            AsyncInventory("todo", SQLiteStorage(str(tmp_path / "x.db")))  # type: ignore[arg-type]


class TestAsyncInventorySave:
    async def test_save_returns_stored_item(self, todos):
        assert await todos.save({"id": "1", "title": "Buy milk"}) == {"id": "1", "title": "Buy milk"}

    async def test_save_stores_under_item_type(self, todos, storage):
        await todos.save({"id": "1"})
        assert storage.read("todo", "1") == {"id": "1"}

    @pytest.mark.parametrize("item", [{}, {"id": ""}, {"id": None}])
    async def test_save_without_id_raises(self, todos, item):
        with pytest.raises(ValueError, match="id is required"):
            await todos.save(item)

    async def test_save_raises_when_storage_write_fails(self):
        with pytest.raises(InventoryError, match="Failed to save"):
            await AsyncInventory("todo", FailingStorage()).save({"id": "1"})


class TestAsyncInventoryKeys:
    async def test_keys_returns_ids(self, todos):
        await todos.save({"id": "1"})
        await todos.save({"id": "2"})
        assert sorted(await todos.keys()) == ["1", "2"]

    async def test_keys_empty(self, todos):
        assert await todos.keys() == []

    async def test_keys_only_for_own_item_type(self, todos, storage):
        await todos.save({"id": "1"})
        await AsyncInventory("note", storage).save({"id": "2"})
        assert await todos.keys() == ["1"]

    async def test_keys_reflects_delete(self, todos):
        await todos.save({"id": "1"})
        await todos.save({"id": "2"})
        await todos.delete("1")
        assert await todos.keys() == ["2"]


class TestAsyncInventoryGetFilter:
    async def test_get_returns_item(self, todos):
        await todos.save({"id": "1", "title": "a"})
        assert await todos.get("1") == {"id": "1", "title": "a"}

    async def test_get_missing_returns_none(self, todos):
        assert await todos.get("nope") is None

    async def test_filter_returns_all_items(self, todos):
        await todos.save({"id": "1"})
        await todos.save({"id": "2"})
        assert sorted(i["id"] for i in await todos.filter()) == ["1", "2"]

    async def test_filter_empty(self, todos):
        assert await todos.filter() == []


class TestAsyncInventoryPatch:
    async def test_patch_merges_fields(self, todos):
        await todos.save({"id": "1", "title": "a", "done": False})
        assert await todos.patch("1", {"done": True}) == {"id": "1", "title": "a", "done": True}

    async def test_patch_persists(self, todos):
        await todos.save({"id": "1", "done": False})
        await todos.patch("1", {"done": True})
        assert await todos.get("1") == {"id": "1", "done": True}

    async def test_patch_cannot_change_id(self, todos):
        await todos.save({"id": "1"})
        with pytest.raises(ValueError, match="must not change the item id"):
            await todos.patch("1", {"id": "2"})
        assert await todos.get("2") is None

    async def test_patch_missing_item_raises(self, todos):
        with pytest.raises(ItemNotFoundError) as exc_info:
            await todos.patch("nope", {"done": True})
        assert exc_info.value.item_type == "todo"
        assert exc_info.value.id == "nope"

    async def test_patch_raises_when_storage_write_fails(self):
        storage = FailingStorage()
        storage.write("todo", {"id": "1"})
        with pytest.raises(InventoryError, match="Failed to patch"):
            await AsyncInventory("todo", storage).patch("1", {"done": True})


class TestAsyncInventoryDelete:
    async def test_delete_existing(self, todos):
        await todos.save({"id": "1"})
        assert await todos.delete("1") is True
        assert await todos.get("1") is None

    async def test_delete_missing(self, todos):
        assert await todos.delete("nope") is False


# ===========================================================================
# AsyncPydanticInventory
# ===========================================================================


class Todo(pydantic.BaseModel):
    id: str
    title: str
    done: bool = False


@pytest.fixture()
def model_todos(storage) -> AsyncPydanticInventory[Todo]:
    return AsyncPydanticInventory(item_type="todo", storage=storage, model_class=Todo)


class TestAsyncPydanticInventory:
    def test_exposes_item_type_and_storage(self, model_todos, storage):
        assert model_todos.item_type == "todo"
        assert model_todos.storage is storage

    def test_rejects_sync_only_storage(self, tmp_path):
        with pytest.raises(TypeError, match="not an AsyncStorage"):
            AsyncPydanticInventory("todo", SQLiteStorage(str(tmp_path / "x.db")), Todo)  # type: ignore[arg-type]

    async def test_save_returns_model(self, model_todos):
        result = await model_todos.save(Todo(id="1", title="Buy milk"))
        assert result == Todo(id="1", title="Buy milk")

    async def test_save_stores_plain_dict(self, model_todos, storage):
        await model_todos.save(Todo(id="1", title="Buy milk"))
        assert storage.read("todo", "1") == {"id": "1", "title": "Buy milk", "done": False}

    async def test_get_returns_model(self, model_todos):
        await model_todos.save(Todo(id="1", title="a"))
        assert isinstance(await model_todos.get("1"), Todo)

    async def test_get_missing_returns_none(self, model_todos):
        assert await model_todos.get("nope") is None

    async def test_keys_returns_ids(self, model_todos):
        await model_todos.save(Todo(id="1", title="a"))
        await model_todos.save(Todo(id="2", title="b"))
        assert sorted(await model_todos.keys()) == ["1", "2"]

    async def test_keys_does_not_validate_items(self, model_todos, storage):
        storage.write("todo", {"id": "1", "title": "a", "done": "not a bool"})  # written outside the model
        assert await model_todos.keys() == ["1"]
        with pytest.raises(pydantic.ValidationError):
            await model_todos.filter()

    async def test_filter_returns_models(self, model_todos):
        await model_todos.save(Todo(id="1", title="a"))
        await model_todos.save(Todo(id="2", title="b"))
        result = await model_todos.filter()
        assert all(isinstance(t, Todo) for t in result)
        assert sorted(t.id for t in result) == ["1", "2"]

    async def test_patch_with_dict(self, model_todos):
        await model_todos.save(Todo(id="1", title="a"))
        assert await model_todos.patch("1", {"done": True}) == Todo(id="1", title="a", done=True)

    async def test_patch_with_model(self, model_todos):
        await model_todos.save(Todo(id="1", title="a"))
        todo = await model_todos.get("1")
        todo.done = True
        assert await model_todos.patch("1", todo) == Todo(id="1", title="a", done=True)

    async def test_patch_missing_raises(self, model_todos):
        with pytest.raises(ItemNotFoundError) as exc_info:
            await model_todos.patch("nope", {"done": True})
        assert exc_info.value.item_type == "todo"

    async def test_patch_cannot_change_id(self, model_todos):
        await model_todos.save(Todo(id="1", title="a"))
        with pytest.raises(ValueError, match="must not change the item id"):
            await model_todos.patch("1", {"id": "2"})

    async def test_invalid_patch_is_not_stored(self, model_todos, storage):
        await model_todos.save(Todo(id="1", title="a"))
        with pytest.raises(pydantic.ValidationError):
            await model_todos.patch("1", {"done": "not a bool"})
        assert storage.read("todo", "1") == {"id": "1", "title": "a", "done": False}
        assert await model_todos.filter() == [Todo(id="1", title="a")]

    async def test_invalid_model_is_not_stored(self, model_todos, storage):
        todo = Todo(id="1", title="a")
        todo.done = "not a bool"  # type: ignore[assignment]  # Pydantic does not validate assignment by default
        with pytest.raises(pydantic.ValidationError):
            await model_todos.save(todo)
        assert storage.read("todo", "1") is None

    async def test_delete(self, model_todos):
        await model_todos.save(Todo(id="1", title="a"))
        assert await model_todos.delete("1") is True
        assert await model_todos.get("1") is None
