import json
from typing import Any, Protocol

from objbase.interface import Item, Storage

DEFAULT_KEY_PREFIX = "objbase:"


class RedisHashClient(Protocol):
    """The Redis hash commands the Redis adapters use.

    Satisfied by ``redis.Redis`` and ``redis.asyncio.Redis`` (and compatible
    clients). Return types are ``Any`` because redis-py annotates every command
    as returning ``Awaitable[T] | T``; the async adapter awaits the results.
    """

    def hkeys(self, name: str, /) -> Any: ...

    def hvals(self, name: str, /) -> Any: ...

    def hget(self, name: str, key: str, /) -> Any: ...

    def hset(self, name: str, key: str, value: str, /) -> Any: ...

    def hdel(self, name: str, /, *keys: str) -> Any: ...


def decode_key(key: bytes | str) -> str:
    """Hash field names are bytes unless the client was created with ``decode_responses=True``."""
    return key.decode() if isinstance(key, bytes) else key


def redis_type_key(key_prefix: str, item_type: str) -> str:
    """Name of the Redis hash that holds all items of ``item_type``, keyed by id."""
    return f"{key_prefix}{item_type}"


class RedisStorage(Storage):
    """Redis-backed storage.

    Each item type is one Redis hash (``{key_prefix}{item_type}``) mapping item
    ids to JSON-encoded items. Works with clients created with or without
    ``decode_responses=True``.
    """

    def __init__(self, redis_client: RedisHashClient, key_prefix: str = DEFAULT_KEY_PREFIX):
        self.redis_client = redis_client
        self.key_prefix = key_prefix

    def _key(self, item_type: str) -> str:
        return redis_type_key(self.key_prefix, item_type)

    def keys(self, item_type: str) -> list[str]:
        return [decode_key(key) for key in self.redis_client.hkeys(self._key(item_type))]

    def items(self, item_type: str) -> list[Item]:
        return [json.loads(value) for value in self.redis_client.hvals(self._key(item_type))]

    def write(self, item_type: str, item: Item) -> bool:
        self.redis_client.hset(self._key(item_type), item["id"], json.dumps(item))
        return True

    def read(self, item_type: str, id: str) -> Item | None:
        value = self.redis_client.hget(self._key(item_type), id)
        return json.loads(value) if value is not None else None

    def delete(self, item_type: str, id: str) -> bool:
        return bool(self.redis_client.hdel(self._key(item_type), id))
