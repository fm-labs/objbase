"""Shared contract tests run against every storage adapter.

Each adapter must behave identically for the operations below (see the
``Storage`` docstring). Adapter-specific behaviour belongs in the
per-adapter test modules.

Redis and MongoDB run in testcontainers and are skipped when Docker is not
available. The MongoDB image can be overridden with OBJBASE_TEST_MONGO_IMAGE.
"""

import os
import shutil
import subprocess
from collections.abc import AsyncIterator

import pytest

from objbase import AsyncStorage
from objbase.interface import Item, Storage
from objbase.storage.inmemory import InMemoryStorage
from objbase.storage.local import (
    LocalDirectoryStorage,
    LocalFileStorage,
)
from objbase.storage.sqlite import SQLiteStorage

# See tests/test_mongodb_storage.py for why mongo:latest is not used.
MONGO_IMAGE = os.getenv("OBJBASE_TEST_MONGO_IMAGE", "mongo:7.0")


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


requires_docker = pytest.mark.skipif(not _docker_available(), reason="Docker is not available")


# ---------------------------------------------------------------------------
# Container fixtures (started lazily, only when a container backend is selected)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def redis_container():
    from testcontainers.community.redis import RedisContainer

    with RedisContainer() as container:
        yield container


@pytest.fixture(scope="module")
def mongo_container():
    from testcontainers.community.mongodb import MongoDbContainer

    with MongoDbContainer(MONGO_IMAGE) as container:
        yield container


# ---------------------------------------------------------------------------
# Sync adapters
# ---------------------------------------------------------------------------


def _inmemory(request, tmp_path):
    return InMemoryStorage()


def _file(request, tmp_path):
    return LocalFileStorage(str(tmp_path))


def _directory(request, tmp_path):
    return LocalDirectoryStorage(str(tmp_path))


def _sqlite(request, tmp_path):
    return SQLiteStorage(str(tmp_path / "inventory.db"))


def _redis(request, tmp_path):
    from objbase.storage.redis import RedisStorage

    client = request.getfixturevalue("redis_container").get_client()
    client.flushdb()
    return RedisStorage(client)


def _mongodb(request, tmp_path):
    from objbase.storage.mongodb import MongoDBStorage

    client = request.getfixturevalue("mongo_container").get_connection_client()
    client.drop_database("inventory")
    return MongoDBStorage(client)


SYNC_ADAPTERS = [
    pytest.param(_inmemory, id="inmemory"),
    pytest.param(_file, id="file"),
    pytest.param(_directory, id="directory"),
    pytest.param(_sqlite, id="sqlite"),
    pytest.param(_redis, id="redis", marks=requires_docker),
    pytest.param(_mongodb, id="mongodb", marks=requires_docker),
]


@pytest.fixture(params=SYNC_ADAPTERS)
def storage(request, tmp_path) -> Storage:
    adapter: Storage = request.param(request, tmp_path)
    return adapter


class TestStorageContract:
    def test_implements_protocol(self, storage):
        assert isinstance(storage, Storage)

    # keys

    def test_keys_unknown_type_returns_empty_list(self, storage):
        assert storage.keys("ghost") == []

    def test_keys_returns_all_ids_of_type(self, storage):
        storage.write("todo", {"id": "1", "title": "a"})
        storage.write("todo", {"id": "2", "title": "b"})
        assert sorted(storage.keys("todo")) == ["1", "2"]

    def test_keys_are_strings(self, storage):
        storage.write("todo", {"id": "1"})
        assert all(type(key) is str for key in storage.keys("todo"))

    def test_keys_isolates_types(self, storage):
        storage.write("todo", {"id": "1"})
        storage.write("note", {"id": "2"})
        assert storage.keys("todo") == ["1"]

    def test_keys_has_no_duplicates_after_overwrite(self, storage):
        storage.write("todo", {"id": "1", "title": "a"})
        storage.write("todo", {"id": "1", "title": "b"})
        assert storage.keys("todo") == ["1"]

    def test_keys_reflects_delete(self, storage):
        storage.write("todo", {"id": "1"})
        storage.write("todo", {"id": "2"})
        storage.delete("todo", "1")
        assert storage.keys("todo") == ["2"]

    def test_keys_match_ids_of_items(self, storage):
        for i in range(5):
            storage.write("todo", {"id": f"item-{i}", "n": i})
        assert sorted(storage.keys("todo")) == sorted(item["id"] for item in storage.items("todo"))

    # select

    def test_select_unknown_type_returns_empty_list(self, storage):
        assert storage.items("ghost") == []

    def test_select_returns_all_items_of_type(self, storage):
        storage.write("todo", {"id": "1", "title": "a"})
        storage.write("todo", {"id": "2", "title": "b"})
        items = sorted(storage.items("todo"), key=lambda i: i["id"])
        assert items == [{"id": "1", "title": "a"}, {"id": "2", "title": "b"}]

    def test_select_isolates_types(self, storage):
        storage.write("todo", {"id": "1", "title": "a"})
        storage.write("note", {"id": "1", "title": "b"})
        assert storage.items("todo") == [{"id": "1", "title": "a"}]

    def test_select_after_all_deleted_returns_empty_list(self, storage):
        storage.write("todo", {"id": "1"})
        storage.delete("todo", "1")
        assert storage.items("todo") == []

    # read

    def test_read_unknown_id_returns_none(self, storage):
        storage.write("todo", {"id": "1"})
        assert storage.read("todo", "999") is None

    def test_read_unknown_type_returns_none(self, storage):
        assert storage.read("ghost", "1") is None

    def test_read_returns_written_item(self, storage):
        item = {"id": "1", "title": "Buy milk"}
        storage.write("todo", item)
        assert storage.read("todo", "1") == item

    # write

    def test_write_returns_true(self, storage):
        assert storage.write("todo", {"id": "1"}) is True

    def test_write_replaces_whole_item(self, storage):
        storage.write("todo", {"id": "1", "title": "a", "note": "remove me"})
        storage.write("todo", {"id": "1", "title": "b"})
        assert storage.read("todo", "1") == {"id": "1", "title": "b"}
        assert len(storage.items("todo")) == 1

    def test_write_does_not_mutate_input(self, storage):
        item = {"id": "1", "title": "a"}
        storage.write("todo", item)
        assert item == {"id": "1", "title": "a"}

    def test_write_preserves_value_types(self, storage):
        item = {"id": "1", "done": False, "count": 3, "ratio": 0.5, "tags": ["a"], "meta": {"k": "v"}}
        storage.write("todo", item)
        assert storage.read("todo", "1") == item

    # delete

    def test_delete_existing_returns_true(self, storage):
        storage.write("todo", {"id": "1"})
        assert storage.delete("todo", "1") is True
        assert storage.read("todo", "1") is None

    def test_delete_unknown_id_returns_false(self, storage):
        storage.write("todo", {"id": "1"})
        assert storage.delete("todo", "999") is False
        assert storage.read("todo", "1") == {"id": "1"}

    def test_delete_unknown_type_returns_false(self, storage):
        assert storage.delete("ghost", "1") is False

    def test_delete_only_removes_target(self, storage):
        storage.write("todo", {"id": "1"})
        storage.write("todo", {"id": "2"})
        storage.write("note", {"id": "1"})
        storage.delete("todo", "1")
        assert storage.items("todo") == [{"id": "2"}]
        assert storage.read("note", "1") == {"id": "1"}

    # isolation

    def test_mutating_input_after_write_does_not_change_stored_item(self, storage):
        item = {"id": "1", "title": "a"}
        storage.write("todo", item)
        item["title"] = "changed"
        assert storage.read("todo", "1") == {"id": "1", "title": "a"}

    def test_mutating_read_result_does_not_change_stored_item(self, storage):
        storage.write("todo", {"id": "1", "title": "a"})
        storage.read("todo", "1")["title"] = "changed"
        storage.items("todo")[0]["title"] = "changed"
        assert storage.read("todo", "1") == {"id": "1", "title": "a"}


# ---------------------------------------------------------------------------
# Async adapters
# ---------------------------------------------------------------------------


async def _async_inmemory(request):
    return InMemoryStorage()


async def _async_file(request):
    from objbase.asyncio.storage.local import AsyncLocalFileStorage

    return AsyncLocalFileStorage(str(request.getfixturevalue("tmp_path")))


async def _async_directory(request):
    from objbase.asyncio.storage.local import AsyncLocalDirectoryStorage

    return AsyncLocalDirectoryStorage(str(request.getfixturevalue("tmp_path")))


async def _async_sqlite(request):
    from objbase.asyncio.storage.sqlite import AsyncSQLiteStorage

    return AsyncSQLiteStorage(str(request.getfixturevalue("tmp_path") / "contract.db"))


async def _async_redis(request):
    import redis.asyncio

    from objbase.asyncio.storage.redis import AsyncRedisStorage

    container = request.getfixturevalue("redis_container")
    client = redis.asyncio.Redis(
        host=container.get_container_host_ip(),
        port=int(container.get_exposed_port(6379)),
        decode_responses=True,
    )
    await client.flushdb()
    return AsyncRedisStorage(client)


async def _async_mongodb(request):
    import pymongo

    from objbase.asyncio.storage.mongodb import AsyncMongoDBStorage

    url = request.getfixturevalue("mongo_container").get_connection_url()
    client: pymongo.AsyncMongoClient[Item] = pymongo.AsyncMongoClient(url)
    await client.drop_database("inventory")
    return AsyncMongoDBStorage(client)


ASYNC_ADAPTERS = [
    pytest.param(_async_inmemory, id="inmemory"),
    pytest.param(_async_file, id="file"),
    pytest.param(_async_directory, id="directory"),
    pytest.param(_async_sqlite, id="sqlite"),
    pytest.param(_async_redis, id="redis", marks=requires_docker),
    pytest.param(_async_mongodb, id="mongodb", marks=requires_docker),
]


@pytest.fixture(params=ASYNC_ADAPTERS)
async def async_storage(request) -> AsyncIterator[AsyncStorage]:
    storage = await request.param(request)
    yield storage
    client = getattr(storage, "redis_client", None)
    if client is not None:
        await client.aclose()
    mongo_client = getattr(storage, "mongo_client", None)
    if mongo_client is not None:
        await mongo_client.close()


class TestAsyncStorageContract:
    def test_implements_protocol(self, async_storage):
        assert isinstance(async_storage, AsyncStorage)

    async def test_keys_unknown_type_returns_empty_list(self, async_storage):
        assert await async_storage.akeys("ghost") == []

    async def test_keys_returns_ids_as_strings(self, async_storage):
        await async_storage.awrite("todo", {"id": "1"})
        await async_storage.awrite("todo", {"id": "2"})
        await async_storage.awrite("note", {"id": "3"})
        keys = await async_storage.akeys("todo")
        assert sorted(keys) == ["1", "2"]
        assert all(type(key) is str for key in keys)

    async def test_keys_has_no_duplicates_and_reflects_delete(self, async_storage):
        await async_storage.awrite("todo", {"id": "1", "v": 1})
        await async_storage.awrite("todo", {"id": "1", "v": 2})
        await async_storage.awrite("todo", {"id": "2"})
        await async_storage.adelete("todo", "2")
        assert await async_storage.akeys("todo") == ["1"]

    async def test_keys_match_ids_of_items(self, async_storage):
        for i in range(5):
            await async_storage.awrite("todo", {"id": f"item-{i}"})
        items = await async_storage.aitems("todo")
        assert sorted(await async_storage.akeys("todo")) == sorted(item["id"] for item in items)

    async def test_select_unknown_type_returns_empty_list(self, async_storage):
        assert await async_storage.aitems("ghost") == []

    async def test_read_unknown_returns_none(self, async_storage):
        assert await async_storage.aread("ghost", "1") is None

    async def test_read_returns_written_item(self, async_storage):
        item = {"id": "1", "title": "Buy milk"}
        assert await async_storage.awrite("todo", item) is True
        assert await async_storage.aread("todo", "1") == item

    async def test_write_preserves_value_types(self, async_storage):
        item = {"id": "1", "done": False, "count": 3, "ratio": 0.5, "tags": ["a"], "meta": {"k": "v"}}
        await async_storage.awrite("todo", item)
        assert await async_storage.aread("todo", "1") == item

    async def test_write_replaces_whole_item(self, async_storage):
        await async_storage.awrite("todo", {"id": "1", "title": "a", "note": "remove me"})
        await async_storage.awrite("todo", {"id": "1", "title": "b"})
        assert await async_storage.aread("todo", "1") == {"id": "1", "title": "b"}

    async def test_delete_returns_whether_item_existed(self, async_storage):
        await async_storage.awrite("todo", {"id": "1"})
        assert await async_storage.adelete("todo", "1") is True
        assert await async_storage.adelete("todo", "1") is False
        assert await async_storage.aread("todo", "1") is None
