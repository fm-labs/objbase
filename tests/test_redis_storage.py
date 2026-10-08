"""Tests for RedisStorage using a real Redis via testcontainers."""

import json

import pytest
from testcontainers.community.redis import RedisContainer

from objbase.storage.redis import RedisStorage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def redis_container():
    """Start a single Redis container for the entire test session."""
    with RedisContainer() as container:
        yield container


@pytest.fixture()
def redis_client(redis_container):
    """Return a bytes-mode Redis client and flush the DB before each test."""
    client = redis_container.get_client()
    client.flushdb()
    return client


@pytest.fixture()
def storage(redis_client) -> RedisStorage:
    return RedisStorage(redis_client)


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


class TestRedisStorageWrite:
    def test_write_returns_true(self, storage):
        assert storage.write("todo", {"id": "1", "title": "Buy milk"}) is True

    def test_write_stores_item_as_json_in_type_hash(self, storage, redis_client):
        storage.write("todo", {"id": "1", "title": "Buy milk"})
        raw = redis_client.hget("inventory:todo", "1")
        assert json.loads(raw) == {"id": "1", "title": "Buy milk"}

    def test_write_preserves_value_types(self, storage):
        item = {"id": "1", "done": False, "count": 3, "ratio": 0.5, "tags": ["a"], "meta": {"k": None}}
        storage.write("todo", item)
        assert storage.read("todo", "1") == item
        assert storage.items("todo") == [item]

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
            storage.write("todo", {"id": str(i), "val": str(i)})
        assert len(storage.items("todo")) == 3


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


class TestRedisStorageRead:
    def test_read_returns_item_by_id(self, storage):
        item = {"id": "42", "title": "Hello"}
        storage.write("todo", item)
        assert storage.read("todo", "42") == item

    def test_read_returns_none_for_unknown_id(self, storage):
        assert storage.read("todo", "nonexistent") is None

    def test_read_returns_none_for_unknown_type(self, storage):
        assert storage.read("ghost_type", "1") is None

    def test_read_returns_correct_item_among_many(self, storage):
        for i in range(5):
            storage.write("todo", {"id": str(i), "val": str(i)})
        assert storage.read("todo", "3") == {"id": "3", "val": "3"}

    def test_read_does_not_cross_types(self, storage):
        storage.write("todos", {"id": "1", "kind": "todo"})
        assert storage.read("notes", "1") is None


# ---------------------------------------------------------------------------
# select
# ---------------------------------------------------------------------------


class TestRedisStorageSelect:
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


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestRedisStorageDelete:
    def test_delete_returns_true_when_item_exists(self, storage):
        storage.write("todo", {"id": "1"})
        assert storage.delete("todo", "1") is True

    def test_delete_returns_false_for_unknown_id(self, storage):
        assert storage.delete("todo", "nonexistent") is False

    def test_delete_returns_false_for_unknown_type(self, storage):
        assert storage.delete("ghost_type", "1") is False

    def test_delete_removes_item_from_redis(self, storage, redis_client):
        storage.write("todo", {"id": "1"})
        storage.delete("todo", "1")
        assert not redis_client.hexists("inventory:todo", "1")

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


# ---------------------------------------------------------------------------
# key layout & client configuration
# ---------------------------------------------------------------------------


class TestRedisStorageLayout:
    def test_works_with_decode_responses_client(self, redis_container, redis_client):
        client = redis_container.get_client(decode_responses=True)
        storage = RedisStorage(client)
        item = {"id": "1", "done": True}
        storage.write("todo", item)
        assert storage.read("todo", "1") == item
        assert storage.items("todo") == [item]
        assert storage.keys("todo") == ["1"]
        assert storage.delete("todo", "1") is True

    def test_bytes_and_str_clients_share_data(self, redis_container, storage):
        storage.write("todo", {"id": "1", "count": 2})
        str_storage = RedisStorage(redis_container.get_client(decode_responses=True))
        assert str_storage.read("todo", "1") == {"id": "1", "count": 2}

    def test_types_sharing_a_prefix_do_not_collide(self, storage):
        storage.write("todo", {"id": "1"})
        storage.write("todo:archive", {"id": "2"})
        storage.write("todo", {"id": "archive:2"})
        assert sorted(i["id"] for i in storage.items("todo")) == ["1", "archive:2"]
        assert storage.items("todo:archive") == [{"id": "2"}]

    def test_custom_key_prefix(self, redis_client):
        storage = RedisStorage(redis_client, key_prefix="myapp:")
        storage.write("todo", {"id": "1"})
        assert redis_client.hexists("myapp:todo", "1")
        assert not redis_client.exists("inventory:todo")

    def test_different_prefixes_are_isolated(self, redis_client):
        a = RedisStorage(redis_client, key_prefix="a:")
        b = RedisStorage(redis_client, key_prefix="b:")
        a.write("todo", {"id": "1"})
        assert b.read("todo", "1") is None
        assert b.items("todo") == []
