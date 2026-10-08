"""Tests for AsyncLocalFileStorage and AsyncLocalDirectoryStorage."""

import asyncio
import os
import threading

import pytest

from objbase.asyncio.inventory import AsyncInventory
from objbase.asyncio.storage.local import AsyncLocalDirectoryStorage, AsyncLocalFileStorage
from objbase.storage.local import LocalDirectoryStorage, LocalFileStorage

ADAPTERS = [
    pytest.param((AsyncLocalFileStorage, LocalFileStorage), id="file"),
    pytest.param((AsyncLocalDirectoryStorage, LocalDirectoryStorage), id="directory"),
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_dir(tmp_path) -> str:
    return str(tmp_path)


@pytest.fixture(params=ADAPTERS)
def adapter_classes(request):
    return request.param


@pytest.fixture()
def storage(adapter_classes, base_dir):
    async_cls, _ = adapter_classes
    return async_cls(base_dir)


@pytest.fixture()
def sync_storage(adapter_classes, base_dir):
    _, sync_cls = adapter_classes
    return sync_cls(base_dir)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


class TestAsyncFileStorageInit:
    def test_init_requires_existing_base_dir(self, adapter_classes, tmp_path):
        async_cls, _ = adapter_classes
        with pytest.raises(ValueError, match="does not exist"):
            async_cls(str(tmp_path / "missing"))

    def test_exposes_inventory_dir(self, storage, base_dir):
        assert storage.inventory_dir == base_dir


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestAsyncFileStorageCrud:
    async def test_write_and_read(self, storage):
        item = {"id": "1", "title": "x", "done": False, "priority": 2, "tags": ["a"]}
        assert await storage.awrite("todo", item) is True
        assert await storage.aread("todo", "1") == item

    async def test_write_updates_existing_item(self, storage):
        await storage.awrite("todo", {"id": "1", "title": "Old"})
        await storage.awrite("todo", {"id": "1", "title": "New"})
        assert await storage.aitems("todo") == [{"id": "1", "title": "New"}]

    async def test_read_returns_none_for_unknown_id(self, storage):
        assert await storage.aread("todo", "nonexistent") is None

    async def test_unknown_type_is_empty(self, storage):
        assert await storage.aitems("ghost") == []
        assert await storage.akeys("ghost") == []
        assert await storage.adelete("ghost", "1") is False

    async def test_keys_returns_ids(self, storage):
        await storage.awrite("todo", {"id": "1"})
        await storage.awrite("todo", {"id": "2"})
        assert sorted(await storage.akeys("todo")) == ["1", "2"]

    async def test_delete(self, storage):
        await storage.awrite("todo", {"id": "1"})
        await storage.awrite("todo", {"id": "2"})
        assert await storage.adelete("todo", "1") is True
        assert await storage.adelete("todo", "1") is False
        assert await storage.aitems("todo") == [{"id": "2"}]


# ---------------------------------------------------------------------------
# behaviour
# ---------------------------------------------------------------------------


class TestAsyncFileStorageBehaviour:
    async def test_rejects_unsafe_item_type(self, storage):
        with pytest.raises(ValueError, match="Invalid item type"):
            await storage.awrite("../escape", {"id": "1"})

    async def test_shares_data_with_sync_storage(self, storage, sync_storage):
        sync_storage.write("todo", {"id": "1", "n": 1})
        assert await storage.aread("todo", "1") == {"id": "1", "n": 1}
        await storage.awrite("todo", {"id": "2", "n": 2})
        assert sync_storage.read("todo", "2") == {"id": "2", "n": 2}

    async def test_runs_off_the_event_loop_thread(self, storage, monkeypatch):
        threads = []
        original = storage.sync_storage.write

        def recording_write(item_type, item):
            threads.append(threading.current_thread())
            return original(item_type, item)

        monkeypatch.setattr(storage.sync_storage, "write", recording_write)
        await storage.awrite("todo", {"id": "1"})
        assert threads and threads[0] is not threading.current_thread()

    async def test_concurrent_writes_are_not_lost(self, storage):
        """Writes run in parallel threads; the file locks must keep every one of them."""
        await asyncio.gather(*(storage.awrite("todo", {"id": str(i)}) for i in range(30)))
        assert sorted(await storage.akeys("todo"), key=int) == [str(i) for i in range(30)]
        assert len(await storage.aitems("todo")) == 30

    async def test_works_with_async_inventory(self, storage):
        todos = AsyncInventory(item_type="todo", storage=storage)
        await todos.save({"id": "1", "done": False})
        assert await todos.patch("1", {"done": True}) == {"id": "1", "done": True}


class TestAsyncLocalDirectoryStorageIndex:
    async def test_rebuild_index(self, base_dir):
        storage = AsyncLocalDirectoryStorage(base_dir)
        await storage.awrite("todo", {"id": "1"})
        await storage.awrite("todo", {"id": "2"})
        os.remove(os.path.join(base_dir, "todo", "2.json"))  # index now lists a missing item

        await storage.arebuild_index("todo")

        with open(os.path.join(base_dir, "todo", ".index")) as f:
            assert f.read().splitlines() == ["1"]
