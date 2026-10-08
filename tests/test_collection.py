"""Tests for the Collection and PydanticCollection APIs."""

import pydantic
import pytest

from objbase.collection import Collection
from objbase.errors import CollectionError, ItemNotFoundError
from objbase.pydantic import PydanticCollection
from objbase.storage.inmemory import InMemoryStorage


@pytest.fixture()
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture()
def todos(storage) -> Collection:
    return Collection(item_type="todo", storage=storage)


class FailingStorage(InMemoryStorage):
    def write(self, item_type, item):
        return False


# ===========================================================================
# Collection
# ===========================================================================


class TestCollectionSave:
    def test_save_returns_stored_item(self, todos):
        assert todos.save({"id": "1", "title": "Buy milk"}) == {"id": "1", "title": "Buy milk"}

    def test_save_stores_under_item_type(self, todos, storage):
        todos.save({"id": "1"})
        assert storage.read("todo", "1") == {"id": "1"}

    @pytest.mark.parametrize("item", [{}, {"id": ""}, {"id": None}])
    def test_save_without_id_raises(self, todos, item):
        with pytest.raises(ValueError, match="id is required"):
            todos.save(item)

    def test_save_raises_when_storage_write_fails(self):
        with pytest.raises(CollectionError, match="Failed to save"):
            Collection("todo", FailingStorage()).save({"id": "1"})


class TestCollectionKeys:
    def test_keys_returns_ids(self, todos):
        todos.save({"id": "1"})
        todos.save({"id": "2"})
        assert sorted(todos.keys()) == ["1", "2"]

    def test_keys_empty(self, todos):
        assert todos.keys() == []

    def test_keys_only_for_own_item_type(self, todos, storage):
        todos.save({"id": "1"})
        Collection("note", storage).save({"id": "2"})
        assert todos.keys() == ["1"]

    def test_keys_reflects_delete(self, todos):
        todos.save({"id": "1"})
        todos.save({"id": "2"})
        todos.delete("1")
        assert todos.keys() == ["2"]


class TestCollectionGetFilter:
    def test_get_returns_item(self, todos):
        todos.save({"id": "1", "title": "a"})
        assert todos.get("1") == {"id": "1", "title": "a"}

    def test_get_missing_returns_none(self, todos):
        assert todos.get("nope") is None

    def test_items_returns_all_items(self, todos):
        todos.save({"id": "1"})
        todos.save({"id": "2"})
        assert sorted(i["id"] for i in todos.items()) == ["1", "2"]

    def test_items_empty(self, todos):
        assert todos.items() == []


class TestCollectionPatch:
    def test_patch_merges_fields(self, todos):
        todos.save({"id": "1", "title": "a", "done": False})
        assert todos.patch("1", {"done": True}) == {"id": "1", "title": "a", "done": True}

    def test_patch_persists(self, todos):
        todos.save({"id": "1", "done": False})
        todos.patch("1", {"done": True})
        assert todos.get("1") == {"id": "1", "done": True}

    def test_patch_adds_new_fields(self, todos):
        todos.save({"id": "1"})
        assert todos.patch("1", {"extra": 1}) == {"id": "1", "extra": 1}

    def test_patch_with_same_id_allowed(self, todos):
        todos.save({"id": "1", "title": "a"})
        assert todos.patch("1", {"id": "1", "title": "b"}) == {"id": "1", "title": "b"}

    def test_patch_cannot_change_id(self, todos):
        todos.save({"id": "1"})
        with pytest.raises(ValueError, match="must not change the item id"):
            todos.patch("1", {"id": "2"})
        assert todos.get("2") is None

    def test_patch_missing_item_raises(self, todos):
        with pytest.raises(ItemNotFoundError) as exc_info:
            todos.patch("nope", {"done": True})
        assert exc_info.value.item_type == "todo"
        assert exc_info.value.id == "nope"
        assert isinstance(exc_info.value, LookupError)

    def test_patch_raises_when_storage_write_fails(self):
        storage = FailingStorage()
        InMemoryStorage.write(storage, "todo", {"id": "1"})
        with pytest.raises(CollectionError, match="Failed to patch"):
            Collection("todo", storage).patch("1", {"done": True})


class TestCollectionDelete:
    def test_delete_existing(self, todos):
        todos.save({"id": "1"})
        assert todos.delete("1") is True
        assert todos.get("1") is None

    def test_delete_missing(self, todos):
        assert todos.delete("nope") is False


# ===========================================================================
# PydanticCollection
# ===========================================================================


class Todo(pydantic.BaseModel):
    id: str
    title: str
    done: bool = False


@pytest.fixture()
def model_todos(storage) -> PydanticCollection[Todo]:
    return PydanticCollection(item_type="todo", storage=storage, model_class=Todo)


class TestPydanticCollection:
    def test_exposes_item_type_and_storage(self, model_todos, storage):
        assert model_todos.item_type == "todo"
        assert model_todos.storage is storage

    def test_save_returns_model(self, model_todos):
        result = model_todos.save(Todo(id="1", title="Buy milk"))
        assert result == Todo(id="1", title="Buy milk")

    def test_save_stores_plain_dict(self, model_todos, storage):
        model_todos.save(Todo(id="1", title="Buy milk"))
        assert storage.read("todo", "1") == {"id": "1", "title": "Buy milk", "done": False}

    def test_get_returns_model(self, model_todos):
        model_todos.save(Todo(id="1", title="a"))
        assert isinstance(model_todos.get("1"), Todo)

    def test_get_missing_returns_none(self, model_todos):
        assert model_todos.get("nope") is None

    def test_keys_returns_ids(self, model_todos):
        model_todos.save(Todo(id="1", title="a"))
        model_todos.save(Todo(id="2", title="b"))
        assert sorted(model_todos.keys()) == ["1", "2"]

    def test_keys_does_not_validate_items(self, model_todos, storage):
        storage.write("todo", {"id": "1", "title": "a", "done": "not a bool"})  # written outside the model
        assert model_todos.keys() == ["1"]
        with pytest.raises(pydantic.ValidationError):
            model_todos.filter()

    def test_items_returns_models(self, model_todos):
        model_todos.save(Todo(id="1", title="a"))
        model_todos.save(Todo(id="2", title="b"))
        result = model_todos.filter()
        assert all(isinstance(t, Todo) for t in result)
        assert sorted(t.id for t in result) == ["1", "2"]

    def test_patch_with_dict(self, model_todos):
        model_todos.save(Todo(id="1", title="a"))
        assert model_todos.patch("1", {"done": True}) == Todo(id="1", title="a", done=True)

    def test_patch_with_model(self, model_todos):
        model_todos.save(Todo(id="1", title="a"))
        todo = model_todos.get("1")
        todo.done = True
        assert model_todos.patch("1", todo) == Todo(id="1", title="a", done=True)

    def test_patch_missing_raises(self, model_todos):
        with pytest.raises(ItemNotFoundError) as exc_info:
            model_todos.patch("nope", {"done": True})
        assert exc_info.value.item_type == "todo"

    def test_patch_cannot_change_id(self, model_todos):
        model_todos.save(Todo(id="1", title="a"))
        with pytest.raises(ValueError, match="must not change the item id"):
            model_todos.patch("1", {"id": "2"})

    def test_invalid_patch_is_not_stored(self, model_todos, storage):
        model_todos.save(Todo(id="1", title="a"))
        with pytest.raises(pydantic.ValidationError):
            model_todos.patch("1", {"done": "not a bool"})
        assert storage.read("todo", "1") == {"id": "1", "title": "a", "done": False}
        assert model_todos.filter() == [Todo(id="1", title="a")]

    def test_invalid_model_is_not_stored(self, model_todos, storage):
        todo = Todo(id="1", title="a")
        todo.done = "not a bool"  # type: ignore[assignment]  # Pydantic does not validate assignment by default
        with pytest.raises(pydantic.ValidationError):
            model_todos.save(todo)
        assert storage.read("todo", "1") is None

    def test_patch_stores_normalized_values(self, model_todos, storage):
        model_todos.save(Todo(id="1", title="a"))
        model_todos.patch("1", {"done": "true"})  # coerced by Pydantic
        assert storage.read("todo", "1") == {"id": "1", "title": "a", "done": True}

    def test_delete(self, model_todos):
        model_todos.save(Todo(id="1", title="a"))
        assert model_todos.delete("1") is True
        assert model_todos.get("1") is None
