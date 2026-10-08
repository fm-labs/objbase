"""Tests for action handlers on Collection and AsyncCollection, and load_action_handler."""

import logging
import threading

import pytest

from objbase.actions import load_action_handler
from objbase.asyncio.collection import AsyncCollection
from objbase.collection import Collection
from objbase.errors import ActionNotFoundError, CollectionError, ItemNotFoundError
from objbase.storage.inmemory import InMemoryStorage


def set_status(item, params):
    return {**item, "status": params["status"]}


def no_change(item, params):
    return None


async def async_set_status(item, params):
    return {**item, "status": params["status"]}


@pytest.fixture()
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture()
def todos(storage) -> Collection:
    todos = Collection(item_type="todo", storage=storage)
    todos.save({"id": "1", "status": "pending"})
    return todos


@pytest.fixture()
def async_todos(storage) -> AsyncCollection:
    storage.write("todo", {"id": "1", "status": "pending"})
    return AsyncCollection(item_type="todo", storage=storage)


# ===========================================================================
# Collection
# ===========================================================================


class TestCollectionRegisterAction:
    def test_registers_handler(self, todos):
        todos.register_action("set_status", set_status)
        assert todos.actions == {"set_status": set_status}

    def test_registering_again_replaces_handler(self, todos):
        todos.register_action("act", set_status)
        todos.register_action("act", no_change)
        assert todos.actions["act"] is no_change

    def test_actions_are_per_collection(self, storage, todos):
        todos.register_action("set_status", set_status)
        assert Collection(item_type="note", storage=storage).actions == {}

    def test_empty_name_raises(self, todos):
        with pytest.raises(ValueError):
            todos.register_action("", set_status)

    def test_async_handler_raises_type_error(self, todos):
        with pytest.raises(TypeError, match="AsyncCollection"):
            todos.register_action("set_status", async_set_status)


class TestCollectionRunAction:
    def test_returned_item_is_saved_and_returned(self, todos):
        todos.register_action("set_status", set_status)
        assert todos.run_action("1", "set_status", {"status": "done"}) == {"id": "1", "status": "done"}
        assert todos.get("1") == {"id": "1", "status": "done"}

    def test_none_leaves_item_unchanged(self, todos):
        todos.register_action("noop", no_change)
        assert todos.run_action("1", "noop") == {"id": "1", "status": "pending"}
        assert todos.get("1") == {"id": "1", "status": "pending"}

    def test_params_default_to_empty_dict(self, todos):
        received = []
        todos.register_action("record", lambda item, params: received.append(params))
        todos.run_action("1", "record")
        assert received == [{}]

    def test_handler_receives_stored_item(self, todos):
        received = []
        todos.register_action("record", lambda item, params: received.append(item))
        todos.run_action("1", "record")
        assert received == [{"id": "1", "status": "pending"}]

    def test_unknown_action_raises(self, todos):
        with pytest.raises(ActionNotFoundError) as exc_info:
            todos.run_action("1", "missing")
        assert exc_info.value.action == "missing"
        assert isinstance(exc_info.value, CollectionError)
        assert isinstance(exc_info.value, LookupError)

    def test_unknown_action_checked_before_item(self, todos):
        with pytest.raises(ActionNotFoundError):
            todos.run_action("nonexistent", "missing")

    def test_missing_item_raises(self, todos):
        todos.register_action("set_status", set_status)
        with pytest.raises(ItemNotFoundError):
            todos.run_action("nonexistent", "set_status", {"status": "done"})

    @pytest.mark.parametrize("result", [{"id": "2", "status": "done"}, {"status": "done"}])
    def test_changing_or_dropping_id_raises(self, todos, result):
        todos.register_action("bad", lambda item, params: result)
        with pytest.raises(ValueError):
            todos.run_action("1", "bad")
        assert todos.get("1") == {"id": "1", "status": "pending"}
        assert todos.get("2") is None

    def test_handler_errors_propagate(self, todos):
        todos.register_action("set_status", set_status)
        with pytest.raises(KeyError):
            todos.run_action("1", "set_status", {})
        assert todos.get("1") == {"id": "1", "status": "pending"}

    def test_logs_at_debug_level(self, todos, caplog):
        todos.register_action("set_status", set_status)
        with caplog.at_level(logging.DEBUG, logger="objbase"):
            todos.run_action("1", "set_status", {"status": "done"})
        assert any("set_status" in record.getMessage() for record in caplog.records)
        assert all(record.levelno == logging.DEBUG for record in caplog.records)


# ===========================================================================
# AsyncCollection
# ===========================================================================


class TestAsyncCollectionActions:
    async def test_async_handler_result_is_saved(self, async_todos):
        async_todos.register_action("set_status", async_set_status)
        assert await async_todos.run_action("1", "set_status", {"status": "done"}) == {"id": "1", "status": "done"}
        assert await async_todos.get("1") == {"id": "1", "status": "done"}

    async def test_sync_handler_runs_in_worker_thread(self, async_todos):
        threads = []

        def handler(item, params):
            threads.append(threading.current_thread())
            return set_status(item, params)

        async_todos.register_action("set_status", handler)
        assert await async_todos.run_action("1", "set_status", {"status": "done"}) == {"id": "1", "status": "done"}
        assert threads and threads[0] is not threading.main_thread()

    async def test_none_leaves_item_unchanged(self, async_todos):
        async_todos.register_action("noop", no_change)
        assert await async_todos.run_action("1", "noop") == {"id": "1", "status": "pending"}

    async def test_unknown_action_raises(self, async_todos):
        with pytest.raises(ActionNotFoundError):
            await async_todos.run_action("1", "missing")

    async def test_missing_item_raises(self, async_todos):
        async_todos.register_action("set_status", async_set_status)
        with pytest.raises(ItemNotFoundError):
            await async_todos.run_action("nonexistent", "set_status", {"status": "done"})

    async def test_changing_id_raises(self, async_todos):
        async def bad(item, params):
            return {"id": "2"}

        async_todos.register_action("bad", bad)
        with pytest.raises(ValueError):
            await async_todos.run_action("1", "bad")
        assert await async_todos.get("2") is None

    def test_empty_name_raises(self, async_todos):
        with pytest.raises(ValueError):
            async_todos.register_action("", set_status)


# ===========================================================================
# load_action_handler
# ===========================================================================


@pytest.fixture()
def actions_module(tmp_path, monkeypatch):
    (tmp_path / "my_todo_actions.py").write_text(
        "def set_status(item, params):\n"
        "    return {**item, 'status': params['status']}\n"
        "\n"
        "actions = {'set_status': set_status, 'broken': 42}\n"
        "handlers = {'other': set_status}\n"
    )
    (tmp_path / "my_failing_actions.py").write_text("import does_not_exist_anywhere\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    return "my_todo_actions"


class TestLoadActionHandler:
    def test_loads_handler_from_actions_mapping(self, actions_module, todos):
        handler = load_action_handler(actions_module, "set_status")
        todos.register_action("set_status", handler)
        assert todos.run_action("1", "set_status", {"status": "done"})["status"] == "done"

    def test_custom_attr_name(self, actions_module):
        assert callable(load_action_handler(actions_module, "other", attr_name="handlers"))

    def test_unknown_action_raises(self, actions_module):
        with pytest.raises(ActionNotFoundError, match="missing"):
            load_action_handler(actions_module, "missing")

    def test_missing_mapping_raises(self, actions_module):
        with pytest.raises(ActionNotFoundError):
            load_action_handler(actions_module, "set_status", attr_name="nope")

    def test_non_callable_raises(self, actions_module):
        with pytest.raises(TypeError):
            load_action_handler(actions_module, "broken")

    def test_missing_module_raises_import_error(self):
        with pytest.raises(ModuleNotFoundError):
            load_action_handler("objbase_no_such_module", "set_status")

    def test_import_errors_inside_module_propagate(self, actions_module):
        with pytest.raises(ModuleNotFoundError, match="does_not_exist_anywhere"):
            load_action_handler("my_failing_actions", "set_status")
