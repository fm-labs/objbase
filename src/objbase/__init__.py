"""Damn simple object store for Python dicts and Pydantic models across multiple backends."""

import importlib
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from objbase.asyncio.collection import AsyncCollection
from objbase.asyncio.storage.local import AsyncLocalDirectoryStorage, AsyncLocalFileStorage
from objbase.asyncio.storage.mongodb import AsyncMongoDBStorage
from objbase.asyncio.storage.redis import AsyncRedisStorage
from objbase.asyncio.storage.sqlite import AsyncSQLiteStorage
from objbase.errors import CollectionError, ItemNotFoundError
from objbase.interface import AsyncStorage, Item, Storage
from objbase.collection import Collection
from objbase.storage.inmemory import InMemoryStorage
from objbase.storage.local import LocalDirectoryStorage, LocalFileStorage
from objbase.storage.mongodb import MongoDBStorage
from objbase.storage.redis import RedisStorage
from objbase.storage.sqlite import SQLiteStorage

if TYPE_CHECKING:
    # Lets type checkers see the real classes; at runtime they are loaded lazily by __getattr__.
    from objbase.pydantic import AsyncPydanticCollection, PydanticCollection

try:
    __version__ = version("objbase")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"

__all__ = [
    "AsyncLocalDirectoryStorage",
    "AsyncLocalFileStorage",
    "AsyncCollection",
    "AsyncStorage",
    "AsyncMongoDBStorage",
    "AsyncPydanticCollection",
    "AsyncRedisStorage",
    "AsyncSQLiteStorage",
    "LocalDirectoryStorage",
    "LocalFileStorage",
    "InMemoryStorage",
    "Collection",
    "CollectionError",
    "Storage",
    "Item",
    "ItemNotFoundError",
    "MongoDBStorage",
    "PydanticCollection",
    "RedisStorage",
    "SQLiteStorage",
]


def __getattr__(name: str) -> Any:
    # Imported lazily so `import objbase` works without pydantic installed.
    if name in ("PydanticCollection", "AsyncPydanticCollection"):
        return getattr(importlib.import_module("objbase.pydantic"), name)
    raise AttributeError(f"module 'objbase' has no attribute {name!r}")
