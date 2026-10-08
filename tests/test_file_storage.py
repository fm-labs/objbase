"""Tests for FileBasedStorage and DirectoryBasedStorage."""

import json
import os
import stat
import subprocess
import sys
import threading

import pytest

from objbase.interface import Item
from objbase.storage.file_storage import (
    DirectoryBasedStorage,
    FileBasedStorage,
)
from objbase.util.file_util import locked

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_dir(tmp_path) -> str:
    return str(tmp_path)


@pytest.fixture()
def file_storage(base_dir) -> FileBasedStorage:
    return FileBasedStorage(base_dir)


@pytest.fixture()
def dir_storage(base_dir) -> DirectoryBasedStorage:
    return DirectoryBasedStorage(base_dir)


def seed_file(base_dir: str, item_type: str, items: list[Item]) -> None:
    """Pre-create a type's JSON file with the given items."""
    path = os.path.join(base_dir, f"{item_type}.json")
    with open(path, "w") as f:
        json.dump(items, f)


# ===========================================================================
# FileBasedStorage
# ===========================================================================


class TestFileBasedStorageInit:
    def test_init_raises_on_missing_dir(self):
        with pytest.raises(ValueError, match="does not exist"):
            FileBasedStorage("/nonexistent/path/xyz")

    def test_init_succeeds_with_existing_dir(self, base_dir):
        storage = FileBasedStorage(base_dir)
        assert storage.inventory_dir == base_dir


class TestFileBasedStorageSelect:
    def test_select_returns_all_items(self, file_storage, base_dir):
        items = [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}]
        seed_file(base_dir, "todo", items)
        assert file_storage.items("todo") == items

    def test_select_returns_empty_list_when_file_missing(self, file_storage):
        assert file_storage.items("nonexistent_type") == []

    def test_select_returns_empty_list_for_empty_file(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [])
        assert file_storage.items("todo") == []


class TestFileBasedStorageWrite:
    def test_write_creates_new_item(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [])
        item = {"id": "1", "title": "Buy milk"}
        file_storage.write("todo", item)
        assert file_storage.items("todo") == [item]

    def test_write_creates_file_for_new_type(self, file_storage, base_dir):
        item = {"id": "1", "title": "Buy milk"}
        file_storage.write("todo", item)
        assert os.path.exists(os.path.join(base_dir, "todo.json"))
        assert file_storage.read("todo", "1") == item

    def test_write_returns_true(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [])
        assert file_storage.write("todo", {"id": "1"}) is True

    def test_write_updates_existing_item(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [{"id": "1", "title": "Old"}])
        file_storage.write("todo", {"id": "1", "title": "New"})
        result = file_storage.items("todo")
        assert len(result) == 1
        assert result[0]["title"] == "New"

    def test_write_update_does_not_duplicate(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [{"id": "1", "title": "x"}])
        file_storage.write("todo", {"id": "1", "title": "y"})
        assert len(file_storage.items("todo")) == 1

    def test_multiple_items_persist(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [])
        for i in range(3):
            file_storage.write("todo", {"id": str(i), "value": i})
        assert len(file_storage.items("todo")) == 3


class TestFileBasedStorageRead:
    def test_read_returns_item_by_id(self, file_storage, base_dir):
        item = {"id": "42", "title": "Hello"}
        seed_file(base_dir, "todo", [item])
        assert file_storage.read("todo", "42") == item

    def test_read_returns_none_when_not_found(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [{"id": "1"}])
        assert file_storage.read("todo", "999") is None

    def test_read_returns_none_when_file_missing(self, file_storage):
        assert file_storage.read("ghost_type", "1") is None

    def test_read_returns_correct_item_among_many(self, file_storage, base_dir):
        items = [{"id": str(i), "val": i} for i in range(5)]
        seed_file(base_dir, "todo", items)
        assert file_storage.read("todo", "3") == {"id": "3", "val": 3}


class TestFileBasedStorageDelete:
    def test_delete_removes_item(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [{"id": "1"}, {"id": "2"}])
        file_storage.delete("todo", "1")
        remaining = file_storage.items("todo")
        assert len(remaining) == 1
        assert remaining[0]["id"] == "2"

    def test_delete_returns_true(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [{"id": "1"}])
        assert file_storage.delete("todo", "1") is True

    def test_delete_returns_false_if_id_missing(self, file_storage, base_dir):
        seed_file(base_dir, "todo", [{"id": "1"}])
        result = file_storage.delete("todo", "nonexistent")
        assert result is False
        # Original item is untouched
        assert len(file_storage.items("todo")) == 1

    def test_delete_returns_false_when_file_missing(self, file_storage):
        assert file_storage.delete("ghost_type", "1") is False


# ===========================================================================
# DirectoryBasedStorage
# ===========================================================================


class TestDirectoryBasedStorageInit:
    def test_init_raises_on_missing_dir(self):
        with pytest.raises(ValueError, match="does not exist"):
            DirectoryBasedStorage("/nonexistent/path/xyz")

    def test_init_succeeds_with_existing_dir(self, base_dir):
        storage = DirectoryBasedStorage(base_dir)
        assert storage.inventory_dir == base_dir


class TestDirectoryBasedStorageSelect:
    def test_select_returns_empty_list_when_type_dir_missing(self, dir_storage):
        assert dir_storage.items("ghost") == []

    def test_select_returns_written_items(self, dir_storage):
        items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        for item in items:
            dir_storage.write("todo", item)
        result = dir_storage.items("todo")
        assert sorted(result, key=lambda x: x["id"]) == sorted(items, key=lambda x: x["id"])

    def test_select_returns_empty_list_for_empty_type_dir(self, dir_storage, base_dir):
        os.makedirs(os.path.join(base_dir, "empty_type"))
        assert dir_storage.items("empty_type") == []

    def test_multiple_types_are_isolated(self, dir_storage):
        dir_storage.write("todos", {"id": "1", "kind": "todo"})
        dir_storage.write("notes", {"id": "1", "kind": "note"})
        todos = dir_storage.items("todos")
        notes = dir_storage.items("notes")
        assert todos == [{"id": "1", "kind": "todo"}]
        assert notes == [{"id": "1", "kind": "note"}]


class TestDirectoryBasedStorageWrite:
    def test_write_returns_true(self, dir_storage):
        assert dir_storage.write("todo", {"id": "1"}) is True

    def test_write_creates_type_directory(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1"})
        assert os.path.isdir(os.path.join(base_dir, "todo"))

    def test_write_creates_individual_json_file(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "abc"})
        assert os.path.isfile(os.path.join(base_dir, "todo", "abc.json"))

    def test_write_raises_on_missing_id(self, dir_storage):
        with pytest.raises(ValueError, match="'id'"):
            dir_storage.write("todo", {"title": "No ID here"})

    def test_write_raises_on_empty_id(self, dir_storage):
        with pytest.raises(ValueError, match="'id'"):
            dir_storage.write("todo", {"id": ""})

    def test_update_via_write_overwrites_fields(self, dir_storage):
        dir_storage.write("todo", {"id": "1", "title": "Original"})
        dir_storage.write("todo", {"id": "1", "title": "Updated"})
        assert dir_storage.read("todo", "1") == {"id": "1", "title": "Updated"}

    def test_update_via_write_does_not_duplicate(self, dir_storage):
        dir_storage.write("todo", {"id": "1"})
        dir_storage.write("todo", {"id": "1"})
        assert len(dir_storage.items("todo")) == 1


class TestDirectoryBasedStorageRead:
    def test_read_returns_item_by_id(self, dir_storage):
        item = {"id": "7", "title": "Test"}
        dir_storage.write("todo", item)
        assert dir_storage.read("todo", "7") == item

    def test_read_returns_none_when_not_found(self, dir_storage):
        dir_storage.write("todo", {"id": "1"})
        assert dir_storage.read("todo", "999") is None

    def test_read_returns_none_when_type_missing(self, dir_storage):
        assert dir_storage.read("ghost_type", "1") is None


class TestDirectoryBasedStorageDelete:
    def test_delete_removes_item_and_returns_true(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1"})
        result = dir_storage.delete("todo", "1")
        assert result is True
        assert not os.path.exists(os.path.join(base_dir, "todo", "1.json"))

    def test_delete_returns_false_when_item_missing(self, dir_storage):
        assert dir_storage.delete("todo", "nonexistent") is False

    def test_delete_only_removes_target_item(self, dir_storage):
        dir_storage.write("todo", {"id": "1"})
        dir_storage.write("todo", {"id": "2"})
        dir_storage.delete("todo", "1")
        remaining = dir_storage.items("todo")
        assert remaining == [{"id": "2"}]


# ===========================================================================
# Path validation (both file-based adapters)
# ===========================================================================


UNSAFE_NAMES = ["", ".", "..", "../escape", "a/b", "..\\escape", "nul\x00byte", "new\nline", "carriage\rreturn"]


class TestFileStoragePathValidation:
    @pytest.mark.parametrize("item_type", UNSAFE_NAMES)
    def test_file_storage_rejects_unsafe_item_type(self, file_storage, item_type):
        with pytest.raises(ValueError, match="Invalid item type"):
            file_storage.write(item_type, {"id": "1"})

    @pytest.mark.parametrize("item_type", UNSAFE_NAMES)
    def test_dir_storage_rejects_unsafe_item_type(self, dir_storage, item_type):
        with pytest.raises(ValueError, match="Invalid item type"):
            dir_storage.write(item_type, {"id": "1"})

    @pytest.mark.parametrize("item_id", [n for n in UNSAFE_NAMES if n])
    def test_dir_storage_rejects_unsafe_item_id(self, dir_storage, item_id):
        with pytest.raises(ValueError, match="Invalid item id"):
            dir_storage.write("todo", {"id": item_id})
        with pytest.raises(ValueError, match="Invalid item id"):
            dir_storage.read("todo", item_id)
        with pytest.raises(ValueError, match="Invalid item id"):
            dir_storage.delete("todo", item_id)

    def test_dir_storage_traversal_writes_nothing_outside_base_dir(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        storage = DirectoryBasedStorage(str(base))
        with pytest.raises(ValueError):
            storage.write("todo", {"id": "../../escaped"})
        assert list(tmp_path.rglob("escaped*")) == []


def symlink(target: str, link: str) -> None:
    try:
        os.symlink(target, link)
    except OSError as e:  # Windows without symlink privilege
        pytest.skip(f"cannot create symlinks: {e}")


class TestFileStorageSymlinkContainment:
    """Symlinks inside the base dir must not let reads or writes reach files outside it."""

    @pytest.fixture()
    def outside(self, tmp_path) -> str:
        path = tmp_path / "outside"
        path.mkdir()
        (path / "secret.json").write_text(json.dumps({"id": "secret"}))
        return str(path)

    @pytest.fixture()
    def base_dir(self, tmp_path) -> str:
        path = tmp_path / "base"
        path.mkdir()
        return str(path)

    def test_dir_storage_rejects_symlinked_type_dir(self, dir_storage, base_dir, outside):
        symlink(outside, os.path.join(base_dir, "todo"))
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.write("todo", {"id": "planted"})
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.read("todo", "secret")
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.keys("todo")
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.items("todo")
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.delete("todo", "secret")
        assert sorted(os.listdir(outside)) == ["secret.json"]

    def test_dir_storage_rejects_symlinked_item_file(self, dir_storage, base_dir, outside):
        dir_storage.write("todo", {"id": "1"})
        symlink(os.path.join(outside, "secret.json"), os.path.join(base_dir, "todo", "leak.json"))
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.read("todo", "leak")
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.items("todo")
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.write("todo", {"id": "leak"})
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.delete("todo", "leak")
        assert os.path.exists(os.path.join(outside, "secret.json"))

    def test_dir_storage_rejects_symlinked_index_and_lock(self, dir_storage, base_dir, outside):
        dir_storage.write("todo", {"id": "1"})
        type_dir = os.path.join(base_dir, "todo")
        os.remove(os.path.join(type_dir, ".index"))
        symlink(os.path.join(outside, "index"), os.path.join(type_dir, ".index"))
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.write("todo", {"id": "2"})
        os.remove(os.path.join(type_dir, ".index"))
        os.remove(os.path.join(type_dir, ".index.lock"))
        symlink(os.path.join(outside, "lock"), os.path.join(type_dir, ".index.lock"))
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.keys("todo")
        assert sorted(os.listdir(outside)) == ["secret.json"]

    def test_file_storage_rejects_symlinked_type_file(self, file_storage, base_dir, outside):
        symlink(os.path.join(outside, "secret.json"), os.path.join(base_dir, "todo.json"))
        with pytest.raises(ValueError, match="outside the base directory"):
            file_storage.items("todo")
        with pytest.raises(ValueError, match="outside the base directory"):
            file_storage.write("todo", {"id": "1"})
        with pytest.raises(ValueError, match="outside the base directory"):
            file_storage.delete("todo", "secret")

    def test_file_storage_rejects_symlinked_lock_file(self, file_storage, base_dir, outside):
        symlink(os.path.join(outside, "lock"), os.path.join(base_dir, ".todo.json.lock"))
        with pytest.raises(ValueError, match="outside the base directory"):
            file_storage.write("todo", {"id": "1"})
        assert sorted(os.listdir(outside)) == ["secret.json"]

    def test_symlink_to_base_dir_itself_is_rejected(self, dir_storage, base_dir):
        symlink(base_dir, os.path.join(base_dir, "todo"))
        with pytest.raises(ValueError, match="outside the base directory"):
            dir_storage.keys("todo")

    def test_symlinks_within_base_dir_are_allowed(self, dir_storage, base_dir):
        os.makedirs(os.path.join(base_dir, "archive", "todo"))
        symlink(os.path.join(base_dir, "archive", "todo"), os.path.join(base_dir, "todo"))
        dir_storage.write("todo", {"id": "1"})
        assert dir_storage.read("todo", "1") == {"id": "1"}
        assert os.path.exists(os.path.join(base_dir, "archive", "todo", "1.json"))

    def test_symlinked_base_dir_is_allowed(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        symlink(str(real), str(tmp_path / "link"))
        for storage in (
                DirectoryBasedStorage(str(tmp_path / "link")),
                FileBasedStorage(str(tmp_path / "link")),
        ):
            storage.write("todo", {"id": "1"})
            assert storage.read("todo", "1") == {"id": "1"}

    def test_extended_length_prefix_from_realpath_is_ignored(self, dir_storage, monkeypatch):
        # On Windows, realpath() can return "\\?\C:\..." for a missing file when its
        # parent directory is created by another thread while it's resolving.
        real_realpath = os.path.realpath
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(os.path, "realpath", lambda p: "\\\\?\\" + real_realpath(p))
        assert dir_storage._item_path("todo", "1").endswith("1.json")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path semantics")
class TestFileStorageWindowsNames:
    @pytest.mark.parametrize(
        "name", ["C:evil", "todo:stream", "a<b", "a>b", 'a"b', "a|b", "a?b", "a*b", "todo.", "todo ", ".. "]
    )
    def test_rejects_windows_unsafe_names(self, file_storage, dir_storage, name):
        with pytest.raises(ValueError, match="Invalid item type"):
            file_storage.write(name, {"id": "1"})
        with pytest.raises(ValueError, match="Invalid item type"):
            dir_storage.write(name, {"id": "1"})
        with pytest.raises(ValueError, match="Invalid item id"):
            dir_storage.write("todo", {"id": name})


# ===========================================================================
# Concurrency and crash safety
# ===========================================================================


WRITER_PROCESS = """
import sys
from objbase.storage.file_storage import FileBasedStorage
storage = FileBasedStorage(sys.argv[1])
for i in range(int(sys.argv[3])):
    storage.write("todo", {"id": f"{sys.argv[2]}-{i}"})
"""


class TestFileBasedStorageConcurrency:
    def test_concurrent_processes_do_not_lose_writes(self, file_storage, base_dir):
        workers, per_worker = 4, 25
        procs = [
            subprocess.Popen([sys.executable, "-c", WRITER_PROCESS, base_dir, str(w), str(per_worker)])
            for w in range(workers)
        ]
        for p in procs:
            assert p.wait(timeout=60) == 0
        assert len(file_storage.items("todo")) == workers * per_worker

    def test_concurrent_threads_do_not_lose_writes(self, file_storage):
        def worker(w: int) -> None:
            for i in range(25):
                file_storage.write("todo", {"id": f"{w}-{i}"})

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert len(file_storage.items("todo")) == 100

    def test_write_waits_for_lock(self, file_storage, base_dir):
        done = threading.Event()

        def write() -> None:
            file_storage.write("todo", {"id": "1"})
            done.set()

        writer = threading.Thread(target=write)
        with locked(os.path.join(base_dir, ".todo.json.lock")):
            writer.start()
            assert not done.wait(timeout=0.3), "write completed while the lock was held"
        writer.join(timeout=10)
        assert done.is_set()
        assert file_storage.read("todo", "1") == {"id": "1"}

    def test_shared_readers_do_not_block_each_other(self, file_storage, base_dir):
        if sys.platform == "win32":
            pytest.skip("Windows locks are always exclusive")
        file_storage.write("todo", {"id": "1"})
        with locked(os.path.join(base_dir, ".todo.json.lock"), shared=True):
            result = []
            reader = threading.Thread(target=lambda: result.append(file_storage.items("todo")))
            reader.start()
            reader.join(timeout=5)
            assert result == [[{"id": "1"}]]


class TestFileBasedStorageFiles:
    def test_failed_write_keeps_original_file(self, file_storage, base_dir):
        file_storage.write("todo", {"id": "1"})
        with pytest.raises(TypeError):
            file_storage.write("todo", {"id": "2", "bad": object()})  # not JSON-serializable
        assert file_storage.items("todo") == [{"id": "1"}]

    def test_no_temp_files_left_behind(self, file_storage, base_dir):
        file_storage.write("todo", {"id": "1"})
        with pytest.raises(TypeError):
            file_storage.write("todo", {"id": "2", "bad": object()})
        assert sorted(os.listdir(base_dir)) == [".todo.json.lock", "todo.json"]

    def test_read_and_delete_of_missing_type_create_no_files(self, file_storage, base_dir):
        assert file_storage.keys("ghost") == []
        assert file_storage.items("ghost") == []
        assert file_storage.read("ghost", "1") is None
        assert file_storage.delete("ghost", "1") is False
        assert os.listdir(base_dir) == []

    def test_lock_file_is_not_an_item_type(self, file_storage, base_dir):
        file_storage.write("todo", {"id": "1"})
        assert file_storage.items(".todo") == []

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
    def test_write_keeps_file_permissions(self, file_storage, base_dir):
        file_storage.write("todo", {"id": "1"})
        path = os.path.join(base_dir, "todo.json")
        os.chmod(path, 0o600)
        file_storage.write("todo", {"id": "2"})
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


class TestDirectoryBasedStorageFiles:
    def test_failed_write_leaves_no_partial_item(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1"})
        with pytest.raises(TypeError):
            dir_storage.write("todo", {"id": "2", "bad": object()})
        assert dir_storage.items("todo") == [{"id": "1"}]
        assert dir_storage.read("todo", "2") is None

    def test_failed_overwrite_keeps_previous_version(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1", "v": 1})
        with pytest.raises(TypeError):
            dir_storage.write("todo", {"id": "1", "bad": object()})
        assert dir_storage.read("todo", "1") == {"id": "1", "v": 1}
        assert sorted(os.listdir(os.path.join(base_dir, "todo"))) == [".index", ".index.lock", "1.json"]


def read_index(base_dir: str, item_type: str) -> list[str]:
    with open(os.path.join(base_dir, item_type, ".index")) as f:
        return f.read().splitlines()


DIR_WRITER_PROCESS = """
import sys
from objbase.storage.file_storage import DirectoryBasedStorage
storage = DirectoryBasedStorage(sys.argv[1])
for i in range(int(sys.argv[3])):
    storage.write("todo", {"id": f"{sys.argv[2]}-{i}"})
    if i % 2:
        storage.delete("todo", f"{sys.argv[2]}-{i}")
"""


class TestDirectoryBasedStorageIndex:
    def test_write_appends_id_to_index(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1"})
        dir_storage.write("todo", {"id": "2"})
        assert read_index(base_dir, "todo") == ["1", "2"]

    def test_overwrite_does_not_duplicate_id(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1", "v": 1})
        dir_storage.write("todo", {"id": "1", "v": 2})
        assert read_index(base_dir, "todo") == ["1"]

    def test_delete_removes_id_from_index(self, dir_storage, base_dir):
        for i in ("1", "2", "3"):
            dir_storage.write("todo", {"id": i})
        assert dir_storage.delete("todo", "2") is True
        assert read_index(base_dir, "todo") == ["1", "3"]
        assert dir_storage.keys("todo") == ["1", "3"]

    def test_delete_of_missing_item_leaves_index_unchanged(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1"})
        assert dir_storage.delete("todo", "2") is False
        assert read_index(base_dir, "todo") == ["1"]

    def test_failed_write_does_not_add_id(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1"})
        with pytest.raises(TypeError):
            dir_storage.write("todo", {"id": "2", "bad": object()})
        assert read_index(base_dir, "todo") == ["1"]

    def test_keys_reads_index_without_scanning_directory(self, dir_storage, base_dir, monkeypatch):
        dir_storage.write("todo", {"id": "1"})
        dir_storage.write("todo", {"id": "2"})

        def no_listdir(path):
            raise AssertionError("keys() scanned the directory")

        monkeypatch.setattr(os, "listdir", no_listdir)
        assert dir_storage.keys("todo") == ["1", "2"]

    def test_keys_does_not_open_item_files(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1"})
        with open(os.path.join(base_dir, "todo", "1.json"), "w") as f:
            f.write("not json")  # items() would fail on this; keys() must not read it
        assert dir_storage.keys("todo") == ["1"]

    def test_index_files_are_not_items(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1"})
        assert dir_storage.items("todo") == [{"id": "1"}]
        assert dir_storage.keys("todo") == ["1"]

    def test_type_dir_without_index_is_scanned(self, dir_storage, base_dir):
        # Data written before indexing existed: item files but no index.
        type_dir = os.path.join(base_dir, "todo")
        os.makedirs(type_dir)
        for name in ("1.json", "2.json", "notes.txt", ".1.json.abc123.tmp"):
            with open(os.path.join(type_dir, name), "w") as f:
                json.dump({"id": name.split(".")[0]}, f)
        assert sorted(dir_storage.keys("todo")) == ["1", "2"]

    def test_first_write_indexes_existing_items(self, dir_storage, base_dir):
        type_dir = os.path.join(base_dir, "todo")
        os.makedirs(type_dir)
        with open(os.path.join(type_dir, "old.json"), "w") as f:
            json.dump({"id": "old"}, f)
        dir_storage.write("todo", {"id": "new"})
        assert sorted(read_index(base_dir, "todo")) == ["new", "old"]

    def test_first_delete_indexes_remaining_items(self, dir_storage, base_dir):
        type_dir = os.path.join(base_dir, "todo")
        os.makedirs(type_dir)
        for i in ("1", "2"):
            with open(os.path.join(type_dir, f"{i}.json"), "w") as f:
                json.dump({"id": i}, f)
        assert dir_storage.delete("todo", "1") is True
        assert read_index(base_dir, "todo") == ["2"]

    def test_rebuild_index_resyncs_with_item_files(self, dir_storage, base_dir):
        dir_storage.write("todo", {"id": "1"})
        dir_storage.write("todo", {"id": "2"})
        type_dir = os.path.join(base_dir, "todo")
        os.remove(os.path.join(type_dir, "1.json"))  # removed behind the storage's back
        with open(os.path.join(type_dir, "3.json"), "w") as f:
            json.dump({"id": "3"}, f)
        dir_storage.rebuild_index("todo")
        assert sorted(dir_storage.keys("todo")) == ["2", "3"]

    def test_rebuild_index_of_missing_type_creates_nothing(self, dir_storage, base_dir):
        dir_storage.rebuild_index("ghost")
        assert os.listdir(base_dir) == []

    def test_read_and_delete_of_missing_type_create_no_files(self, dir_storage, base_dir):
        assert dir_storage.keys("ghost") == []
        assert dir_storage.delete("ghost", "1") is False
        assert os.listdir(base_dir) == []

    def test_concurrent_processes_keep_index_in_sync(self, dir_storage, base_dir):
        workers, per_worker = 4, 25
        procs = [
            subprocess.Popen([sys.executable, "-c", DIR_WRITER_PROCESS, base_dir, str(w), str(per_worker)])
            for w in range(workers)
        ]
        for p in procs:
            assert p.wait(timeout=60) == 0
        expected = sorted(f"{w}-{i}" for w in range(workers) for i in range(0, per_worker, 2))
        assert sorted(read_index(base_dir, "todo")) == expected
        assert sorted(item["id"] for item in dir_storage.items("todo")) == expected
