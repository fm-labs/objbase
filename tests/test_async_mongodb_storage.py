"""Tests for AsyncMongoDBStorage using a real MongoDB via testcontainers."""

import os
from typing import Any

import pymongo
import pytest
from testcontainers.community.mongodb import MongoDbContainer

from objbase.asyncio.storage.mongodb_storage import AsyncMongoDBStorage

# See tests/test_mongodb_storage.py for why mongo:latest is not used.
MONGO_IMAGE = os.getenv("INVENTORYDB_TEST_MONGO_IMAGE", "mongo:7.0")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def mongo_container():
    """Start a single MongoDB container for the entire test session."""
    with MongoDbContainer(MONGO_IMAGE) as container:
        yield container


@pytest.fixture()
async def mongo_client(mongo_container):
    """Return an AsyncMongoClient and drop the inventory DB before each test."""
    client: pymongo.AsyncMongoClient[dict[str, Any]] = pymongo.AsyncMongoClient(mongo_container.get_connection_url())
    await client.drop_database("inventory")
    yield client
    await client.close()


@pytest.fixture()
async def storage(mongo_client) -> AsyncMongoDBStorage:
    return AsyncMongoDBStorage(mongo_client)


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


class TestAsyncMongoDBStorageWrite:
    async def test_write_returns_true(self, storage):
        assert await storage.awrite("todo", {"id": "1", "title": "Buy milk"}) is True

    async def test_write_stores_all_fields(self, storage):
        item = {"id": "1", "title": "Buy milk", "done": False, "priority": 2}
        await storage.awrite("todo", item)
        assert await storage.aread("todo", "1") == item

    async def test_write_updates_existing_item(self, storage):
        await storage.awrite("todo", {"id": "1", "title": "Old"})
        await storage.awrite("todo", {"id": "1", "title": "New"})
        assert (await storage.aread("todo", "1"))["title"] == "New"

    async def test_write_update_does_not_duplicate(self, storage):
        await storage.awrite("todo", {"id": "1", "title": "x"})
        await storage.awrite("todo", {"id": "1", "title": "y"})
        assert len(await storage.aitems("todo")) == 1

    async def test_write_multiple_items(self, storage):
        for i in range(3):
            await storage.awrite("todo", {"id": str(i), "val": i})
        assert len(await storage.aitems("todo")) == 3


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


class TestAsyncMongoDBStorageRead:
    async def test_read_returns_item_by_id(self, storage):
        item = {"id": "42", "title": "Hello"}
        await storage.awrite("todo", item)
        assert await storage.aread("todo", "42") == item

    async def test_read_returns_none_for_unknown_id(self, storage):
        assert await storage.aread("todo", "nonexistent") is None

    async def test_read_returns_none_for_unknown_type(self, storage):
        assert await storage.aread("ghost_type", "1") is None

    async def test_read_does_not_cross_types(self, storage):
        await storage.awrite("todos", {"id": "1", "kind": "todo"})
        assert await storage.aread("notes", "1") is None

    async def test_read_does_not_expose_mongo_id(self, storage):
        await storage.awrite("todo", {"id": "1", "title": "x"})
        assert "_id" not in await storage.aread("todo", "1")


# ---------------------------------------------------------------------------
# select
# ---------------------------------------------------------------------------


class TestAsyncMongoDBStorageSelect:
    async def test_select_returns_empty_list_for_unknown_type(self, storage):
        assert await storage.aitems("todo") == []

    async def test_select_returns_all_items(self, storage):
        items = [{"id": "1", "title": "a"}, {"id": "2", "title": "b"}]
        for item in items:
            await storage.awrite("todo", item)
        result = sorted(await storage.aitems("todo"), key=lambda x: x["id"])
        assert result == sorted(items, key=lambda x: x["id"])

    async def test_select_isolates_types(self, storage):
        await storage.awrite("todos", {"id": "1", "kind": "todo"})
        await storage.awrite("notes", {"id": "1", "kind": "note"})
        assert await storage.aitems("todos") == [{"id": "1", "kind": "todo"}]
        assert await storage.aitems("notes") == [{"id": "1", "kind": "note"}]

    async def test_select_does_not_expose_mongo_id(self, storage):
        await storage.awrite("todo", {"id": "1", "title": "x"})
        for item in await storage.aitems("todo"):
            assert "_id" not in item

    async def test_select_with_query_filters_results(self, storage):
        await storage.awrite("todo", {"id": "1", "done": True})
        await storage.awrite("todo", {"id": "2", "done": False})
        await storage.awrite("todo", {"id": "3", "done": True})
        result = await storage.aitems("todo", query={"done": True})
        assert sorted(r["id"] for r in result) == ["1", "3"]

    async def test_select_with_empty_query_returns_all(self, storage):
        for i in range(3):
            await storage.awrite("todo", {"id": str(i)})
        assert len(await storage.aitems("todo", query={})) == 3


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------


class TestAsyncMongoDBStorageKeys:
    async def test_keys_returns_ids(self, storage):
        await storage.awrite("todo", {"id": "1"})
        await storage.awrite("todo", {"id": "2"})
        assert sorted(await storage.akeys("todo")) == ["1", "2"]

    async def test_keys_returns_empty_list_for_unknown_type(self, storage):
        assert await storage.akeys("ghost_type") == []


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestAsyncMongoDBStorageDelete:
    async def test_delete_returns_true_when_item_exists(self, storage):
        await storage.awrite("todo", {"id": "1"})
        assert await storage.adelete("todo", "1") is True

    async def test_delete_returns_false_for_unknown_id(self, storage):
        assert await storage.adelete("todo", "nonexistent") is False

    async def test_delete_returns_false_for_unknown_type(self, storage):
        assert await storage.adelete("ghost_type", "1") is False

    async def test_delete_item_no_longer_readable(self, storage):
        await storage.awrite("todo", {"id": "1"})
        await storage.adelete("todo", "1")
        assert await storage.aread("todo", "1") is None

    async def test_delete_only_removes_target_item(self, storage):
        await storage.awrite("todo", {"id": "1"})
        await storage.awrite("todo", {"id": "2"})
        await storage.adelete("todo", "1")
        assert await storage.aitems("todo") == [{"id": "2"}]

    async def test_delete_only_removes_target_type(self, storage):
        await storage.awrite("todos", {"id": "1"})
        await storage.awrite("notes", {"id": "1"})
        await storage.adelete("todos", "1")
        assert await storage.aitems("todos") == []
        assert await storage.aitems("notes") == [{"id": "1"}]


class TestAsyncMongoDBStorageLayout:
    async def test_shares_data_with_sync_storage(self, mongo_container, storage):
        from objbase.storage.mongodb_storage import MongoDBStorage

        MongoDBStorage(mongo_container.get_connection_client()).write("todo", {"id": "1", "n": 1})
        assert await storage.aread("todo", "1") == {"id": "1", "n": 1}
