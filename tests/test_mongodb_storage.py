"""Tests for MongoDBStorage using a real MongoDB via testcontainers."""

import os

import pytest
from testcontainers.community.mongodb import MongoDbContainer

from objbase.storage.mongodb import DEFAULT_DB_NAME, MongoDBStorage

# mongo:latest (8.x) refuses to start on Linux kernels >= 6.19 (SERVER-121912),
# which recent Docker Desktop VMs ship. Pin a known-good image by default.
MONGO_IMAGE = os.getenv("OBJBASE_TEST_MONGO_IMAGE", "mongo:7.0")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def mongo_container():
    """Start a single MongoDB container for the entire test session."""
    with MongoDbContainer(MONGO_IMAGE) as container:
        yield container


@pytest.fixture()
def mongo_client(mongo_container):
    """Return a MongoClient and drop the collection DB before each test."""
    client = mongo_container.get_connection_client()
    client.drop_database(DEFAULT_DB_NAME)
    return client


@pytest.fixture()
def storage(mongo_client) -> MongoDBStorage:
    return MongoDBStorage(mongo_client)


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


class TestMongoDBStorageWrite:
    def test_write_returns_true(self, storage):
        assert storage.write("todo", {"id": "1", "title": "Buy milk"}) is True

    def test_write_creates_document(self, storage):
        item = {"id": "1", "title": "Buy milk"}
        storage.write("todo", item)
        assert storage.read("todo", "1") == item

    def test_write_stores_all_fields(self, storage):
        item = {"id": "1", "title": "Buy milk", "done": False, "priority": 2}
        storage.write("todo", item)
        assert storage.read("todo", "1") == item

    def test_write_updates_existing_item(self, storage):
        storage.write("todo", {"id": "1", "title": "Old"})
        storage.write("todo", {"id": "1", "title": "New"})
        assert storage.read("todo", "1")["title"] == "New"

    def test_write_update_does_not_duplicate(self, storage):
        storage.write("todo", {"id": "1", "title": "x"})
        storage.write("todo", {"id": "1", "title": "y"})
        assert len(storage.items("todo")) == 1

    def test_write_multiple_items(self, storage):
        for i in range(3):
            storage.write("todo", {"id": str(i), "val": i})
        assert len(storage.items("todo")) == 3

    def test_write_does_not_expose_mongo_id(self, storage):
        storage.write("todo", {"id": "1"})
        result = storage.read("todo", "1")
        assert "_id" not in result


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


class TestMongoDBStorageRead:
    def test_read_returns_item_by_id(self, storage):
        item = {"id": "42", "title": "Hello"}
        storage.write("todo", item)
        assert storage.read("todo", "42") == item

    def test_read_returns_none_for_unknown_id(self, storage):
        """MongoDBStorage.read returns None (not {}) for missing items."""
        assert storage.read("todo", "nonexistent") is None

    def test_read_returns_none_for_unknown_type(self, storage):
        assert storage.read("ghost_type", "1") is None

    def test_read_returns_correct_item_among_many(self, storage):
        for i in range(5):
            storage.write("todo", {"id": str(i), "val": i})
        assert storage.read("todo", "3") == {"id": "3", "val": 3}

    def test_read_does_not_cross_types(self, storage):
        storage.write("todos", {"id": "1", "kind": "todo"})
        assert storage.read("notes", "1") is None

    def test_read_does_not_expose_mongo_id(self, storage):
        storage.write("todo", {"id": "1", "title": "x"})
        result = storage.read("todo", "1")
        assert "_id" not in result


# ---------------------------------------------------------------------------
# select
# ---------------------------------------------------------------------------


class TestMongoDBStorageSelect:
    def test_select_returns_empty_list_for_unknown_type(self, storage):
        assert storage.items("todo") == []

    def test_select_returns_all_items(self, storage):
        items = [{"id": "1", "title": "a"}, {"id": "2", "title": "b"}]
        for item in items:
            storage.write("todo", item)
        result = sorted(storage.items("todo"), key=lambda x: x["id"])
        assert result == sorted(items, key=lambda x: x["id"])

    def test_select_isolates_types(self, storage):
        storage.write("todos", {"id": "1", "kind": "todo"})
        storage.write("notes", {"id": "1", "kind": "note"})
        assert storage.items("todos") == [{"id": "1", "kind": "todo"}]
        assert storage.items("notes") == [{"id": "1", "kind": "note"}]

    def test_select_reflects_updates(self, storage):
        storage.write("todo", {"id": "1", "title": "Old"})
        storage.write("todo", {"id": "1", "title": "New"})
        result = storage.items("todo")
        assert len(result) == 1
        assert result[0]["title"] == "New"

    def test_select_returns_empty_list_after_all_deleted(self, storage):
        storage.write("todo", {"id": "1"})
        storage.delete("todo", "1")
        assert storage.items("todo") == []

    def test_select_does_not_expose_mongo_id(self, storage):
        storage.write("todo", {"id": "1", "title": "x"})
        for item in storage.items("todo"):
            assert "_id" not in item

    def test_select_with_query_filters_results(self, storage):
        storage.write("todo", {"id": "1", "done": True})
        storage.write("todo", {"id": "2", "done": False})
        storage.write("todo", {"id": "3", "done": True})
        result = storage.items("todo", query={"done": True})
        ids = sorted(r["id"] for r in result)
        assert ids == ["1", "3"]

    def test_select_with_empty_query_returns_all(self, storage):
        for i in range(3):
            storage.write("todo", {"id": str(i)})
        assert len(storage.items("todo", query={})) == 3


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestMongoDBStorageDelete:
    def test_delete_returns_true_when_item_exists(self, storage):
        storage.write("todo", {"id": "1"})
        assert storage.delete("todo", "1") is True

    def test_delete_returns_false_for_unknown_id(self, storage):
        assert storage.delete("todo", "nonexistent") is False

    def test_delete_returns_false_for_unknown_type(self, storage):
        assert storage.delete("ghost_type", "1") is False

    def test_delete_item_no_longer_readable(self, storage):
        storage.write("todo", {"id": "1"})
        storage.delete("todo", "1")
        assert storage.read("todo", "1") is None

    def test_delete_item_excluded_from_select(self, storage):
        storage.write("todo", {"id": "1"})
        storage.write("todo", {"id": "2"})
        storage.delete("todo", "1")
        result = storage.items("todo")
        assert result == [{"id": "2"}]

    def test_delete_only_removes_target_type(self, storage):
        storage.write("todos", {"id": "1"})
        storage.write("notes", {"id": "1"})
        storage.delete("todos", "1")
        assert storage.items("todos") == []
        assert storage.items("notes") == [{"id": "1"}]

    def test_delete_only_removes_target_item(self, storage):
        storage.write("todo", {"id": "1"})
        storage.write("todo", {"id": "2"})
        storage.delete("todo", "1")
        assert storage.read("todo", "2") == {"id": "2"}


# ---------------------------------------------------------------------------
# database name
# ---------------------------------------------------------------------------


class TestMongoDBStorageDbName:
    def test_default_db_name(self, storage, mongo_client):
        storage.write("todo", {"id": "1"})
        assert mongo_client["objbase"]["todo"].count_documents({"id": "1"}) == 1

    def test_custom_db_name(self, mongo_client):
        mongo_client.drop_database("myapp")
        storage = MongoDBStorage(mongo_client, db_name="myapp")
        storage.write("todo", {"id": "1"})
        assert mongo_client["myapp"]["todo"].count_documents({"id": "1"}) == 1
        assert "todo" not in mongo_client["objbase"].list_collection_names()

    def test_different_db_names_are_isolated(self, mongo_client):
        mongo_client.drop_database("a")
        mongo_client.drop_database("b")
        a = MongoDBStorage(mongo_client, db_name="a")
        b = MongoDBStorage(mongo_client, db_name="b")
        a.write("todo", {"id": "1"})
        assert b.read("todo", "1") is None
        assert b.items("todo") == []
