import json
import os
import sys

from objbase.interface import Item, Storage
from objbase.util.file_util import atomic_write_json, atomic_write_text, locked

# Newlines are rejected because the directory storage index stores one id per line.
_UNSAFE_CHARS = "/\\\x00\n\r"
if sys.platform == "win32":
    # Characters Windows doesn't allow in file names; ":" would also allow drive-relative
    # paths ("C:x", which os.path.join doesn't anchor to the base dir) and alternate data streams.
    _UNSAFE_CHARS += '<>:"|?*'


def _safe_name(name: str, kind: str) -> str:
    """Validate that an item type or id can be used as a single path component."""
    if not isinstance(name, str) or name in ("", ".", "..") or any(c in name for c in _UNSAFE_CHARS):
        raise ValueError(f"Invalid {kind} for file storage: {name!r}")
    if sys.platform == "win32" and name[-1] in ". ":
        # Windows drops trailing dots and spaces, so "a." would alias "a" and ".. " would mean "..".
        raise ValueError(f"Invalid {kind} for file storage: {name!r}")
    return name


def _strip_extended_prefix(path: str) -> str:
    """Remove a Windows extended-length prefix (``\\\\?\\`` or ``\\\\?\\UNC\\``) from ``path``.

    ``os.path.realpath`` can leave the prefix on a path that doesn't exist yet when
    its parent directory appears while it's resolving (another thread creating a
    type directory), so the result wouldn't compare equal to the unprefixed base.
    """
    if sys.platform == "win32":
        if path.startswith("\\\\?\\UNC\\"):
            return "\\\\" + path[len("\\\\?\\UNC\\") :]
        if path.startswith("\\\\?\\"):
            return path[len("\\\\?\\") :]
    return path


def _contained_path(real_base: str, *parts: str) -> str:
    """Join ``parts`` onto ``real_base``, checking that the real path of the result lies inside ``real_base``.

    ``real_base`` must already be a real path (``os.path.realpath``). Resolving
    symlinks catches links inside the base directory that point outside it, which
    the name checks in ``_safe_name`` can't see. Returns the joined (unresolved)
    path, so replacing or deleting a symlinked file acts on the link itself.

    The check can't stop an attacker who can write to the base directory and swaps
    in a symlink between the check and the file operation.
    """
    path = os.path.join(real_base, *parts)
    real_path = os.path.normcase(_strip_extended_prefix(os.path.realpath(path)))
    base = os.path.normcase(_strip_extended_prefix(real_base))
    try:
        inside = real_path != base and os.path.commonpath([base, real_path]) == base
    except ValueError:  # on different drives (Windows)
        inside = False
    if not inside:
        raise ValueError(f"Path for file storage resolves outside the base directory: {path!r}")
    return path


class LocalFileStorage(Storage):
    """Simple file-based storage that saves all items of a given collection type in a single JSON file.

    Safe for concurrent use by multiple threads and processes on the same machine:
    writes hold an exclusive lock on ``.{item_type}.json.lock`` for the whole
    read-modify-write cycle, and files are replaced atomically. Locks are advisory
    and may not work on network file systems.
    """

    def __init__(self, base_dir: str):
        self.collection_dir = base_dir
        if not os.path.exists(self.collection_dir):
            raise ValueError(f"Base directory {self.collection_dir} does not exist.")
        self._real_base = os.path.realpath(base_dir)

    def keys(self, item_type: str) -> list[str]:
        return [item["id"] for item in self.items(item_type)]

    def items(self, item_type: str) -> list[Item]:
        file_path = self._file_path(item_type)
        if not os.path.exists(file_path):
            return []
        with locked(self._lock_path(item_type), shared=True):
            return self._load(file_path)

    def write(self, item_type: str, item: Item) -> bool:
        file_path = self._file_path(item_type)
        with locked(self._lock_path(item_type)):
            items = self._load(file_path)
            for i, existing_item in enumerate(items):
                if existing_item["id"] == item["id"]:
                    items[i] = item
                    break
            else:
                items.append(item)
            atomic_write_json(file_path, items)
        return True

    def read(self, item_type: str, id: str) -> Item | None:
        items = self.items(item_type)
        for item in items:
            if item["id"] == id:
                return item
        return None

    def delete(self, item_type: str, id: str) -> bool:
        file_path = self._file_path(item_type)
        if not os.path.exists(file_path):
            return False
        with locked(self._lock_path(item_type)):
            items = self._load(file_path)
            remaining = [item for item in items if item["id"] != id]
            if len(remaining) == len(items):
                return False
            atomic_write_json(file_path, remaining)
        return True

    def _file_path(self, item_type: str) -> str:
        return _contained_path(self._real_base, f"{_safe_name(item_type, 'item type')}.json")

    def _lock_path(self, item_type: str) -> str:
        return _contained_path(self._real_base, f".{_safe_name(item_type, 'item type')}.json.lock")

    @staticmethod
    def _load(file_path: str) -> list[Item]:
        """Load a type file; the caller must hold its lock. A missing file means no items."""
        try:
            with open(file_path) as f:
                items: list[Item] = json.load(f)
        except FileNotFoundError:
            return []
        return items


class LocalDirectoryStorage(Storage):
    """Alternative file-based storage that uses a directory per collection type and individual files per item.

    Each type directory also holds an index file (``.index``) listing the ids of
    all items of that type, one per line, so ``keys()`` doesn't have to scan the
    directory. Writes and deletes hold an exclusive lock on ``.index.lock`` while
    they change the item file and the index, keeping both in step across threads
    and processes. Locks are advisory and may not work on network file systems.
    """

    INDEX_FILE = ".index"

    def __init__(self, base_dir: str):
        self.collection_dir = base_dir
        if not os.path.exists(self.collection_dir):
            raise ValueError(f"Base directory {self.collection_dir} does not exist.")
        self._real_base = os.path.realpath(base_dir)

    def _type_dir(self, item_type: str) -> str:
        return _contained_path(self._real_base, _safe_name(item_type, "item type"))

    def _item_path(self, item_type: str, id: str) -> str:
        return self._path_in_type_dir(item_type, f"{_safe_name(id, 'item id')}.json")

    def _path_in_type_dir(self, item_type: str, filename: str) -> str:
        return _contained_path(self._real_base, _safe_name(item_type, "item type"), filename)

    def _index_path(self, item_type: str) -> str:
        return self._path_in_type_dir(item_type, self.INDEX_FILE)

    def _lock_path(self, item_type: str) -> str:
        return self._path_in_type_dir(item_type, f"{self.INDEX_FILE}.lock")

    def keys(self, item_type: str) -> list[str]:
        type_dir = self._type_dir(item_type)
        if not os.path.exists(type_dir):
            return []
        with locked(self._lock_path(item_type), shared=True):
            ids = self._read_index(item_type)
        # A type directory without an index predates indexing; the next write or
        # delete creates the index, until then the directory is scanned.
        return ids if ids is not None else self._scan(type_dir)

    def items(self, item_type: str) -> list[Item]:
        type_dir = self._type_dir(item_type)
        if not os.path.exists(type_dir):
            return []
        items = []
        for filename in os.listdir(type_dir):
            if filename.endswith(".json"):
                try:
                    with open(self._path_in_type_dir(item_type, filename)) as f:
                        items.append(json.load(f))
                except FileNotFoundError:
                    continue  # deleted by another process since listdir()
        return items

    def write(self, item_type: str, item: Item) -> bool:
        item_id = item.get("id")
        if not item_id:
            raise ValueError("Item must have an 'id' field.")
        item_path = self._item_path(item_type, item_id)
        os.makedirs(self._type_dir(item_type), exist_ok=True)
        with locked(self._lock_path(item_type)):
            atomic_write_json(item_path, item)
            if item_id not in self._load_index(item_type):
                with open(self._index_path(item_type), "a") as f:
                    f.write(f"{item_id}\n")
                    f.flush()
                    os.fsync(f.fileno())
        return True

    def read(self, item_type: str, id: str) -> Item | None:
        item_path = self._item_path(item_type, id)
        try:
            with open(item_path) as f:
                item: Item = json.load(f)
        except FileNotFoundError:
            return None
        return item

    def delete(self, item_type: str, id: str) -> bool:
        item_path = self._item_path(item_type, id)
        if not os.path.exists(self._type_dir(item_type)):
            return False
        with locked(self._lock_path(item_type)):
            try:
                os.remove(item_path)
            except FileNotFoundError:
                return False
            ids = self._load_index(item_type)
            if id in ids:
                self._write_index(item_type, [i for i in ids if i != id])
        return True

    def rebuild_index(self, item_type: str) -> None:
        """Recreate the index of ``item_type`` from the item files in its directory.

        Only needed if the index got out of step with the item files, e.g. after a
        crash between writing an item and updating the index, or after item files
        were added or removed by hand.
        """
        type_dir = self._type_dir(item_type)
        if not os.path.exists(type_dir):
            return
        with locked(self._lock_path(item_type)):
            self._write_index(item_type, self._scan(type_dir))

    @staticmethod
    def _scan(type_dir: str) -> list[str]:
        """Ids of all item files in ``type_dir``, from the directory listing (item files are named ``{id}.json``)."""
        return [filename.removesuffix(".json") for filename in os.listdir(type_dir) if filename.endswith(".json")]

    def _read_index(self, item_type: str) -> list[str] | None:
        """Ids in the index of ``item_type``, or ``None`` if there is no index. The caller must hold the lock."""
        try:
            with open(self._index_path(item_type)) as f:
                return [line for line in f.read().splitlines() if line]
        except FileNotFoundError:
            return None

    def _load_index(self, item_type: str) -> list[str]:
        """Like ``_read_index``, but creates a missing index first. The caller must hold the exclusive lock."""
        ids = self._read_index(item_type)
        if ids is None:
            ids = self._scan(self._type_dir(item_type))
            self._write_index(item_type, ids)
        return ids

    def _write_index(self, item_type: str, ids: list[str]) -> None:
        atomic_write_text(self._index_path(item_type), "".join(f"{id}\n" for id in ids))
