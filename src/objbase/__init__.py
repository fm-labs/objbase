"""Damn simple object store for Python dicts and Pydantic models across multiple backends."""

import importlib
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from objbase.asyncio.inventory import AsyncInventory
from objbase.asyncio.storage.file_storage import AsyncDirectoryBasedStorage, AsyncFileBasedStorage
from objbase.asyncio.storage.mongodb_storage import AsyncMongoDBStorage
from objbase.asyncio.storage.redis_storage import AsyncRedisStorage
from objbase.asyncio.storage.sqlite_storage import AsyncSQLiteStorage
from objbase.errors import InventoryError, ItemNotFoundError
from objbase.interface import AsyncStorage, Item, Storage
from objbase.inventory import Inventory
from objbase.storage.file_storage import DirectoryBasedStorage, FileBasedStorage
from objbase.storage.inmemory_storage import InMemoryStorage
from objbase.storage.mongodb_storage import MongoDBStorage
from objbase.storage.redis_storage import RedisStorage
from objbase.storage.sqlite_storage import SQLiteStorage

if TYPE_CHECKING:
    # Lets type checkers see the real classes; at runtime they are loaded lazily by __getattr__.
    from objbase.pydantic import AsyncPydanticInventory, PydanticInventory

try:
    __version__ = version("objbase")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"

__all__ = [
    "AsyncDirectoryBasedStorage",
    "AsyncFileBasedStorage",
    "AsyncInventory",
    "AsyncStorage",
    "AsyncMongoDBStorage",
    "AsyncPydanticInventory",
    "AsyncRedisStorage",
    "AsyncSQLiteStorage",
    "DirectoryBasedStorage",
    "FileBasedStorage",
    "InMemoryStorage",
    "Inventory",
    "InventoryError",
    "Storage",
    "Item",
    "ItemNotFoundError",
    "MongoDBStorage",
    "PydanticInventory",
    "RedisStorage",
    "SQLiteStorage",
]


def __getattr__(name: str) -> Any:
    # Imported lazily so `import objbase` works without pydantic installed.
    if name in ("PydanticInventory", "AsyncPydanticInventory"):
        return getattr(importlib.import_module("objbase.pydantic"), name)
    raise AttributeError(f"module 'objbase' has no attribute {name!r}")
