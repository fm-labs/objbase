"""Tests for AsyncSQLiteStorage."""

import asyncio
import sqlite3
import threading

import pytest

from objbase.asyncio.collection import AsyncCollection
from objbase.asyncio.storage.sqlite import AsyncSQLiteStorage
from objbase.storage.sqlite import SQLiteStorage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture()
def storage(db_path) -> AsyncSQLiteStorage:
    return AsyncSQLiteStorage(db_path)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


class TestAsyncSQLiteStorageInit:
    def test_init_creates_items_table(self, db_path):
        AsyncSQLiteStorage(db_path)
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'").fetchone()
        assert row is not None

    def test_exposes_db_path(self, storage, db_path):
        assert storage.db_path == db_path


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


class TestAsyncSQLiteStorageWrite:
    async def test_write_returns_true(self, storage):
        assert await storage.awrite("todo", {"id": "1", "title": "Buy milk"}) is True

    async def test_write_stores_all_field_types(self, storage):
        item = {"id": "1", "title": "x", "done": False, "priority": 2, "score": 3.14, "tags": ["a"]}
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


# ---------------------------------------------------------------------------
# read / select / keys
# ---------------------------------------------------------------------------


class TestAsyncSQLiteStorageRead:
    async def test_read_returns_none_for_unknown_id(self, storage):
        assert await storage.aread("todo", "nonexistent") is None

    async def test_read_does_not_cross_types(self, storage):
        await storage.awrite("todos", {"id": "1", "kind": "todo"})
        assert await storage.aread("notes", "1") is None

    async def test_select_isolates_types(self, storage):
        await storage.awrite("todos", {"id": "1", "kind": "todo"})
        await storage.awrite("notes", {"id": "1", "kind": "note"})
        assert await storage.aitems("todos") == [{"id": "1", "kind": "todo"}]
        assert await storage.aitems("notes") == [{"id": "1", "kind": "note"}]

    async def test_keys_returns_ids(self, storage):
        await storage.awrite("todo", {"id": "1"})
        await storage.awrite("todo", {"id": "2"})
        assert sorted(await storage.akeys("todo")) == ["1", "2"]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestAsyncSQLiteStorageDelete:
    async def test_delete_returns_true_when_item_exists(self, storage):
        await storage.awrite("todo", {"id": "1"})
        assert await storage.adelete("todo", "1") is True

    async def test_delete_returns_false_for_unknown_id(self, storage):
        assert await storage.adelete("todo", "nonexistent") is False

    async def test_delete_only_removes_target_item(self, storage):
        await storage.awrite("todo", {"id": "1"})
        await storage.awrite("todo", {"id": "2"})
        await storage.adelete("todo", "1")
        assert await storage.aitems("todo") == [{"id": "2"}]


# ---------------------------------------------------------------------------
# behaviour
# ---------------------------------------------------------------------------


class TestAsyncSQLiteStorageBehaviour:
    async def test_shares_data_with_sync_storage(self, db_path, storage):
        SQLiteStorage(db_path).write("todo", {"id": "1", "n": 1})
        assert await storage.aread("todo", "1") == {"id": "1", "n": 1}
        await storage.awrite("todo", {"id": "2", "n": 2})
        assert SQLiteStorage(db_path).read("todo", "2") == {"id": "2", "n": 2}

    async def test_runs_off_the_event_loop_thread(self, storage, monkeypatch):
        threads = []
        original = storage.sync_storage.read

        def recording_read(item_type, id):
            threads.append(threading.current_thread())
            return original(item_type, id)

        monkeypatch.setattr(storage.sync_storage, "read", recording_read)
        await storage.aread("todo", "1")
        assert threads and threads[0] is not threading.current_thread()

    async def test_concurrent_writes(self, storage):
        await asyncio.gather(*(storage.awrite("todo", {"id": str(i)}) for i in range(20)))
        assert sorted(await storage.akeys("todo"), key=int) == [str(i) for i in range(20)]

    async def test_works_with_async_collection(self, storage):
        todos = AsyncCollection(item_type="todo", storage=storage)
        await todos.save({"id": "1", "done": False})
        assert await todos.patch("1", {"done": True}) == {"id": "1", "done": True}
