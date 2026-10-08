"""Tests for InMemoryStorage."""

import pytest

from objbase.storage.inmemory import InMemoryStorage


@pytest.fixture()
def storage() -> InMemoryStorage:
    return InMemoryStorage()


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestInMemoryStorageInit:
    def test_init_creates_empty_store(self):
        storage = InMemoryStorage()
        assert storage.data == {}


# ---------------------------------------------------------------------------
# select
# ---------------------------------------------------------------------------


class TestInMemoryStorageSelect:
    def test_select_returns_empty_list_for_unknown_type(self, storage):
        assert storage.items("todo") == []

    def test_select_returns_all_items(self, storage):
        storage.write("todo", {"id": "1", "title": "a"})
        storage.write("todo", {"id": "2", "title": "b"})
        result = storage.items("todo")
        assert sorted(result, key=lambda x: x["id"]) == [
            {"id": "1", "title": "a"},
            {"id": "2", "title": "b"},
        ]

    def test_select_returns_empty_list_after_all_items_deleted(self, storage):
        storage.write("todo", {"id": "1"})
        storage.delete("todo", "1")
        assert storage.items("todo") == []

    def test_select_isolates_types(self, storage):
        storage.write("todos", {"id": "1", "kind": "todo"})
        storage.write("notes", {"id": "1", "kind": "note"})
        assert storage.items("todos") == [{"id": "1", "kind": "todo"}]
        assert storage.items("notes") == [{"id": "1", "kind": "note"}]


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


class TestInMemoryStorageRead:
    def test_read_returns_item_by_id(self, storage):
        item = {"id": "42", "title": "Hello"}
        storage.write("todo", item)
        assert storage.read("todo", "42") == item

    def test_read_returns_none_for_unknown_id(self, storage):
        storage.write("todo", {"id": "1"})
        assert storage.read("todo", "999") is None

    def test_read_returns_none_for_unknown_type(self, storage):
        assert storage.read("ghost", "1") is None

    def test_read_returns_correct_item_among_many(self, storage):
        for i in range(5):
            storage.write("todo", {"id": str(i), "val": i})
        assert storage.read("todo", "3") == {"id": "3", "val": 3}


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


class TestInMemoryStorageWrite:
    def test_write_returns_true(self, storage):
        assert storage.write("todo", {"id": "1"}) is True

    def test_write_creates_new_item(self, storage):
        storage.write("todo", {"id": "1", "title": "Buy milk"})
        assert storage.read("todo", "1") == {"id": "1", "title": "Buy milk"}

    def test_write_updates_existing_item(self, storage):
        storage.write("todo", {"id": "1", "title": "Old"})
        storage.write("todo", {"id": "1", "title": "New"})
        assert storage.read("todo", "1") == {"id": "1", "title": "New"}

    def test_write_update_does_not_duplicate(self, storage):
        storage.write("todo", {"id": "1"})
        storage.write("todo", {"id": "1"})
        assert len(storage.items("todo")) == 1

    def test_write_multiple_items(self, storage):
        for i in range(3):
            storage.write("todo", {"id": str(i)})
        assert len(storage.items("todo")) == 3

    def test_write_auto_creates_type_namespace(self, storage):
        storage.write("new_type", {"id": "1"})
        assert "new_type" in storage.data


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestInMemoryStorageDelete:
    def test_delete_removes_item(self, storage):
        storage.write("todo", {"id": "1"})
        storage.write("todo", {"id": "2"})
        storage.delete("todo", "1")
        assert storage.read("todo", "1") is None
        assert storage.read("todo", "2") == {"id": "2"}

    def test_delete_returns_true_when_item_exists(self, storage):
        storage.write("todo", {"id": "1"})
        assert storage.delete("todo", "1") is True

    def test_delete_returns_false_when_item_missing(self, storage):
        assert storage.delete("todo", "nonexistent") is False

    def test_delete_returns_false_for_unknown_type(self, storage):
        assert storage.delete("ghost_type", "1") is False

    def test_delete_only_removes_target_item(self, storage):
        storage.write("todo", {"id": "1"})
        storage.write("todo", {"id": "2"})
        storage.delete("todo", "1")
        assert storage.items("todo") == [{"id": "2"}]
