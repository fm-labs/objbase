# objbase

Damn simple object store for Python dicts and Pydantic models across multiple backends
(in-memory, file-based, SQLite, Redis, MongoDB, and more).
Provides a minimal API for storing, retrieving, updating, and deleting objects.

__No thrills__ - **just a simple key-value store for serializable Python objects, with a consistent API across different storage backends.**


## What you get

- Basic CRUD operations: `save`, `get`, `filter`, `keys`, `patch`, `delete`
- Multiple storage adapters (in-memory, file-based, SQLite, Redis, MongoDB)
- Optional Pydantic model validation with `PydanticInventory` / `AsyncPydanticInventory`
- Async support via `AsyncInventory` with async storage adapters (in-memory, file-based, SQLite, Redis, MongoDB)
- Easy FastAPI integration with dependency injection
- Fully typed (ships `py.typed`), checked with `mypy --strict`


---

## Installation

Requires Python 3.13+. The core package has no dependencies; in-memory, file-based
and SQLite storage work out of the box. Install extras for the other backends:

```bash
pip install objbase              # core only
pip install "objbase[redis]"     # + redis-py, for (Async)RedisStorage
pip install "objbase[mongodb]"   # + pymongo, for (Async)MongoDBStorage
pip install "objbase[pydantic]"  # + pydantic, for (Async)PydanticInventory
pip install "objbase[all]"       # everything
# or with uv
uv add "objbase[redis]"
```

---

## Quick Start

Every item must have an `"id"` field. Use `Inventory` with any storage adapter:

```python
from objbase import Inventory, InMemoryStorage

storage = InMemoryStorage()
todos = Inventory(item_type="todo", storage=storage)

todos.save({"id": "1", "title": "Buy milk", "done": False})
todos.save({"id": "2", "title": "Walk dog", "done": False})

todos.get("1")  # → {"id": "1", "title": "Buy milk", "done": False}
todos.filter()  # → [{"id": "1", ...}, {"id": "2", ...}]
todos.keys()  # → ["1", "2"] (order unspecified)
todos.patch("1", {"done": True})  # → {"id": "1", ..., "done": True}
todos.delete("1")  # → True
```

Swapping the backend requires only changing the `storage` argument — the `Inventory`
API stays identical.

All public classes can be imported from the top-level `objbase` package, as above,
or from their submodules (e.g. `objbase.storage.sqlite_storage`) as in the examples below.

### Behaviour

All adapters follow the same contract (verified by a shared test suite):

- `get` returns `None` for a missing item; `filter` and `keys` return `[]` for an empty type.
- `save` inserts a new item or **replaces** an existing one entirely (it does not merge fields).
- `patch` merges the given fields into an existing item. It cannot change the item's `id`.
- `delete` returns `True` if the item was removed, `False` if it did not exist.
- Items you get back are copies; mutating them does not change stored data.

Errors are raised, not returned:

| Situation | Exception |
|---|---|
| `save` an item without an `id` | `ValueError` |
| `patch` a missing item | `objbase.errors.ItemNotFoundError` (a `LookupError`) |
| The storage backend reports a failed write | `objbase.errors.InventoryError` |

---

## Storage Adapters

| Adapter | Sync class | Async class | When to use |
|---|---|---|---|
| In-Memory | `InMemoryStorage` | same class | Testing / prototyping — volatile |
| File (one file per type) | `FileBasedStorage` | `AsyncFileBasedStorage` | Simple persistence for small datasets |
| File (one file per item) | `DirectoryBasedStorage` | `AsyncDirectoryBasedStorage` | Medium datasets; per-item file operations |
| SQLite | `SQLiteStorage` | `AsyncSQLiteStorage` | ACID persistence with zero external deps |
| Redis | `RedisStorage` | `AsyncRedisStorage` | High-performance / distributed access |
| MongoDB | `MongoDBStorage` | `AsyncMongoDBStorage` | Document-oriented storage and complex queries |

Each async adapter uses the same data layout as its sync counterpart, so both can
work on the same data. The file-based and SQLite async adapters run the sync code in
a worker thread (`asyncio.to_thread`) and need no extra dependencies; the Redis and
MongoDB ones use the drivers' native async clients.

### In-Memory

```python
from objbase.storage.inmemory_storage import InMemoryStorage

storage = InMemoryStorage()
```

No configuration needed. Data is lost when the process exits.
Also implements `AsyncStorage` — the async methods delegate to their
sync counterparts.

### File-Based (single file per type)

```python
from objbase.storage.file_storage import FileBasedStorage

storage = FileBasedStorage(base_dir="/var/data/myapp")
```

All items of one type are stored in `{base_dir}/{item_type}.json`.
The directory must exist before construction; type files are created on first write.
Item types must be safe file names, otherwise `ValueError` is raised (see [Path safety](#path-safety)).

Safe to use from multiple threads and processes on the same machine. Each write
holds an exclusive lock on a hidden `.{item_type}.json.lock` file while it reads,
changes and rewrites the type file, so concurrent writes are never lost. Files
are replaced atomically, so readers never see a half-written file and a crash
mid-write cannot corrupt data. Lock files are left in place after use.

Every write rewrites the whole type file, so this adapter suits small datasets.
Locks are advisory and may not work on network file systems (NFS, SMB).

`AsyncFileBasedStorage(base_dir=...)` is the async counterpart. It uses the
same files and locks, running each call in a worker thread (`asyncio.to_thread`),
so it can share a directory with the sync adapter.

### File-Based (one file per item)

```python
from objbase.storage.file_storage import DirectoryBasedStorage

storage = DirectoryBasedStorage(base_dir="/var/data/myapp")
```

Items are stored at `{base_dir}/{item_type}/{id}.json`.
Type directories are created automatically on first write.
Item types and ids must be safe file names, otherwise `ValueError` is raised (see [Path safety](#path-safety)).

Each type directory also contains an index file, `.index`, listing the ids of
all items of that type, one per line. Writes append new ids and deletes remove
them, so `keys()` reads the index instead of scanning the directory. A type
directory without an index (e.g. data written by an older version) is scanned
until the next write or delete creates the index. If the index gets out of step
with the item files — after a crash between writing an item and updating the
index, or after editing item files by hand — call
`storage.rebuild_index(item_type)`. Ids and item types can't contain newlines.

Item files are replaced atomically, so readers never see a half-written item.
Writes and deletes hold an exclusive lock on `.index.lock` in the type
directory while they update the item file and the index, so the index stays
correct with concurrent writers across threads and processes; concurrent writes
to the same item are last-writer-wins. Locks are advisory and may not work on
network file systems (NFS, SMB).

`AsyncDirectoryBasedStorage(base_dir=...)` is the async counterpart. It uses
the same files, index and locks, running each call in a worker thread
(`asyncio.to_thread`); rebuild its index with `await storage.arebuild_index(item_type)`.

### Path safety

Both file-based adapters build file paths from item types (and, for
`DirectoryBasedStorage`, ids), so they guard against path traversal:

- Names must be a single path component: empty names, `.`, `..`, and names
  containing `/`, `\`, NUL or newlines are rejected. On Windows, `< > : " | ? *`
  and trailing dots or spaces are rejected too, since Windows would otherwise
  treat `C:x` as a drive-relative path and `.. ` as `..`.
- Every path is resolved with `os.path.realpath` and must lie inside the base
  directory. A symlink inside the base directory that points outside it (to a
  type file, type directory, item file, index or lock file) makes the operation
  raise `ValueError` instead of following it. Symlinks that stay inside the base
  directory, and a base directory that is itself a symlink, work normally.

The check runs before each file operation, so it doesn't protect against an
attacker who can write to the base directory and swaps in a symlink between the
check and the operation. Don't give untrusted users write access to it.

### SQLite

```python
from objbase.storage.sqlite_storage import SQLiteStorage

storage = SQLiteStorage(db_path="myapp.db")
```

Uses a single `items` table with a `(item_type, id)` primary key and JSON
blob storage. The table is created automatically. No external dependencies needed.
`AsyncSQLiteStorage(db_path=...)` uses the same table, so sync and async adapters
can share a database. It runs each call in a worker thread (`asyncio.to_thread`), so it
also needs no extra dependencies.

### Redis

```python
import redis
from objbase.storage.redis_storage import RedisStorage

client = redis.Redis(host="localhost", port=6379, decode_responses=True)
storage = RedisStorage(redis_client=client)
```

Each item type is one Redis hash, `inventory:{item_type}`, mapping item ids to
JSON-encoded items, so value types (numbers, booleans, lists, nested dicts) are
preserved. Pass `key_prefix="myapp:"` to use a different prefix than `inventory:`.

Pass a pre-configured `redis.Redis` client (sync); `decode_responses` may be on or off.
Requires `redis-py`. `AsyncRedisStorage` takes a `redis.asyncio.Redis` client
and uses the same layout, so sync and async adapters can share data.

### MongoDB

```python
import pymongo
from objbase.storage.mongodb_storage import MongoDBStorage

client = pymongo.MongoClient("mongodb://localhost:27017")
storage = MongoDBStorage(mongo_client=client)
```

Items are stored in the `inventory` database, one collection per `item_type`.
The MongoDB `_id` field is stripped from results automatically.
Pass a pre-configured `pymongo.MongoClient`. Requires `pymongo`. `AsyncMongoDBStorage`
takes a `pymongo.AsyncMongoClient` and uses the same layout, so sync and async adapters
can share data. Both accept an optional MongoDB `query` in `items` / `aitems` to filter results.

---

## Pydantic Models

Use `PydanticInventory` to validate items against a Pydantic `BaseModel`.
`save` and `get` return typed model instances instead of plain dicts.

```python
from pydantic import BaseModel
from objbase.pydantic import PydanticInventory
from objbase.storage.inmemory_storage import InMemoryStorage


class Todo(BaseModel):
  id: str
  title: str
  done: bool = False


todos = PydanticInventory(
  item_type="todo",
  storage=InMemoryStorage(),
  model_class=Todo,
)

todos.save(Todo(id="1", title="Buy milk"))
item = todos.get("1")  # returns a Todo instance (or None), not a dict
if item is not None:
  print(item.done)  # False
```

The model type is inferred from `model_class`, so type checkers know that
`todos.get()` returns `Todo | None` and `todos.filter()` returns `list[Todo]`.
`todos.keys()` returns the item ids (`list[str]`) without loading or validating
any items.

`save` and `patch` validate the complete item before writing it. Data that fails
validation raises `pydantic.ValidationError` and is never stored:

```python
todos.patch("1", {"done": "not a bool"})  # raises ValidationError; item unchanged
```

Items are stored in their validated, JSON-compatible form (`model_dump(mode="json")`),
so values Pydantic coerces are stored normalized: patching `{"done": "true"}` stores `True`.

### Async

`AsyncPydanticInventory` has the same methods and behaviour, as coroutines, and
takes an async storage adapter:

```python
from objbase.pydantic import AsyncPydanticInventory

todos = AsyncPydanticInventory(
    item_type="todo",
    storage=AsyncRedisStorage(redis.asyncio.Redis()),
    model_class=Todo,
)

await todos.save(Todo(id="1", title="Buy milk"))
item = await todos.get("1")  # Todo | None
```

---

## Async Usage

`AsyncInventory` has the same methods and behaviour as `Inventory`, but every
method is a coroutine. It works with any `AsyncStorage` adapter:
`AsyncFileBasedStorage`, `AsyncDirectoryBasedStorage`, `AsyncSQLiteStorage`,
`AsyncRedisStorage`, `AsyncMongoDBStorage`,
or `InMemoryStorage` for tests.

```python
import redis.asyncio
from objbase.asyncio.inventory import AsyncInventory
from objbase.asyncio.storage.redis_storage import AsyncRedisStorage

client = redis.asyncio.Redis(host="localhost", port=6379)
todos = AsyncInventory(item_type="todo", storage=AsyncRedisStorage(client))

await todos.save({"id": "1", "title": "Buy milk", "done": False})
await todos.get("1")  # → {"id": "1", "title": "Buy milk", "done": False}
await todos.filter()  # → [{"id": "1", ...}]
await todos.keys()  # → ["1"]
await todos.patch("1", {"done": True})  # → {"id": "1", ..., "done": True}
await todos.delete("1")  # → True
```

For Pydantic models, use `AsyncPydanticInventory` (see [Pydantic Models: Async](#async)).

Passing a sync-only adapter (e.g. `SQLiteStorage`) to `AsyncInventory`
raises `TypeError`; use its async counterpart (e.g. `AsyncSQLiteStorage`) instead.
The adapter methods (`akeys`, `aitems`, `aread`, `awrite`, `adelete`)
can also be called directly on the storage.

---

## Examples

Runnable scripts are in [`examples/`](examples/):

| Script | Shows |
|---|---|
| `dict_example.py` | `Inventory` with plain dicts (in-memory) |
| `pydantic_example.py` | `PydanticInventory` (in-memory) |
| `async_example.py` | `AsyncInventory` (in-memory) |
| `async_pydantic_example.py` | `AsyncPydanticInventory` (in-memory) |
| `async_file_example.py` | `AsyncFileBasedStorage` |
| `async_directory_example.py` | `AsyncDirectoryBasedStorage`, incl. concurrent saves and `arebuild_index` |
| `async_sqlite_example.py` | `AsyncSQLiteStorage` |
| `mongodb_example.py` | `MongoDBStorage`, incl. a MongoDB `query` filter |
| `async_mongodb_example.py` | `AsyncMongoDBStorage`, incl. a MongoDB `query` filter |

```bash
uv run python examples/async_sqlite_example.py
```

The file-based and SQLite examples write to `data/` in the current directory
(ignored by git); set `INVENTORY_DIR` or `SQLITE_DB_PATH` to change that. The MongoDB
examples need a running server — `docker run --rm -p 27017:27017 mongo:7.0` — and
connect to `MONGODB_URI` (default `mongodb://localhost:27017`).

---

## FastAPI Integration

### 1. Initialise storage with `lifespan`

Use FastAPI's `lifespan` context manager to create the client and storage adapter
once at startup and tear them down cleanly on shutdown.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio
from objbase.asyncio.storage.redis_storage import AsyncRedisStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
  client = redis.asyncio.Redis(host="localhost", port=6379)
  app.state.storage = AsyncRedisStorage(redis_client=client)
  yield
  await client.aclose()


app = FastAPI(lifespan=lifespan)
```

### 2. Inject `AsyncInventory` with `Depends`

Wrap the `AsyncInventory` construction in a dependency function so routes stay clean
and the storage adapter is easy to swap out (e.g. in tests).

```python
from fastapi import Depends, HTTPException, Request
from objbase.asyncio.inventory import AsyncInventory
from objbase.errors import ItemNotFoundError


def get_todos(request: Request) -> AsyncInventory:
  return AsyncInventory(item_type="todo", storage=request.app.state.storage)


@app.get("/todos")
async def list_todos(todos: AsyncInventory = Depends(get_todos)):
  return await todos.filter()


@app.get("/todos/{todo_id}")
async def get_todo(todo_id: str, todos: AsyncInventory = Depends(get_todos)):
  item = await todos.get(todo_id)
  if item is None:
    raise HTTPException(status_code=404)
  return item


@app.post("/todos")
async def create_todo(item: dict, todos: AsyncInventory = Depends(get_todos)):
  return await todos.save(item)


@app.patch("/todos/{todo_id}")
async def update_todo(todo_id: str, data: dict, todos: AsyncInventory = Depends(get_todos)):
  try:
    return await todos.patch(todo_id, data)
  except ItemNotFoundError:
    raise HTTPException(status_code=404)
```

### 3. Sync routes with SQLite

For simpler apps without async requirements, SQLite is the easiest option.
Declare routes without `async def` — FastAPI runs them in a thread pool
automatically, keeping the event loop unblocked.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from objbase.inventory import Inventory
from objbase.storage.sqlite_storage import SQLiteStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
  app.state.storage = SQLiteStorage("app.db")
  yield


app = FastAPI(lifespan=lifespan)


def get_todos(request: Request) -> Inventory:
  return Inventory(item_type="todo", storage=request.app.state.storage)


@app.get("/todos")  # sync — runs in threadpool
def list_todos(todos: Inventory = Depends(get_todos)):
  return todos.filter()
```

### 4. Override the dependency in tests

Swap the storage backend for the entire test run without touching any route code.
`InMemoryStorage` implements the async interface too, so it can stand in
for Redis. Create it once so data persists across requests:

```python
from objbase.asyncio.inventory import AsyncInventory
from objbase.storage.inmemory_storage import InMemoryStorage
from fastapi.testclient import TestClient

test_storage = InMemoryStorage()


def override_todos():
  return AsyncInventory(item_type="todo", storage=test_storage)


app.dependency_overrides[get_todos] = override_todos
client = TestClient(app)
```

### Adapter recommendation by scenario

| Scenario | Recommended adapter |
|---|---|
| Single-process, low traffic | `SQLiteStorage` — zero deps, ACID, simple |
| Multi-worker / multi-process | `RedisStorage` or `MongoDBStorage` |
| Async routes | `AsyncInventory` + `AsyncRedisStorage` or `AsyncMongoDBStorage` — non-blocking, fits the event loop |
| Async routes, single process, no infrastructure | `AsyncInventory` + `AsyncSQLiteStorage` — zero deps, runs in a worker thread |
| Testing / local dev | `InMemoryStorage` — fast, no infrastructure needed |

---

## Writing a Custom Adapter

Both interfaces are defined as `typing.Protocol` with `@runtime_checkable`.
This means **no import or inheritance is required** — any class that implements
the right methods is automatically a valid adapter (structural subtyping).

### Sync — `Storage`

```python
# objbase/interface.py
from typing import Any, Protocol, runtime_checkable

Item = dict[str, Any]


@runtime_checkable
class Storage(Protocol):
    def keys(self, item_type: str) -> list[str]: ...
    def items(self, item_type: str) -> list[Item]: ...
    def read(self, item_type: str, id: str) -> Item | None: ...
    def write(self, item_type: str, item: Item) -> bool: ...
    def delete(self, item_type: str, id: str) -> bool: ...
```

Every adapter must follow this contract (the shared test suite in
`tests/test_storage_contract.py` checks it):

- `keys` returns all item ids of a type as strings, or `[]` if there are none.
- `items` returns all items of a type, or `[]` if there are none.
- `read` returns the item, or `None` if it does not exist.
- `write` inserts the item, or replaces an existing item with the same id entirely.
- `delete` returns `True` if an item was removed, `False` if it did not exist.
- Returned items are independent copies; mutating them does not change stored data.

The order of `keys` and `items` is unspecified.

### Async — `AsyncStorage`

```python
# objbase/asyncio/async_storage.py
from typing import Protocol, runtime_checkable
from objbase.interface import Item


@runtime_checkable
class AsyncStorage(Protocol):
    async def akeys(self, item_type: str) -> list[str]: ...

    async def aitems(self, item_type: str) -> list[Item]: ...

    async def aread(self, item_type: str, id: str) -> Item | None: ...

    async def awrite(self, item_type: str, item: Item) -> bool: ...

    async def adelete(self, item_type: str, id: str) -> bool: ...
```

Same contract as the sync protocol, with every method a coroutine.

### Duck-typing — no inheritance needed

Because `Protocol` uses structural subtyping, a third-party class is a valid
adapter as long as it has the right methods — it does not need to import or
subclass anything from `objbase`:

```python
class MyCustomStorage:
    def keys(self, item_type: str) -> list[str]: ...

    def items(self, item_type: str) -> list[dict]: ...

    def read(self, item_type: str, id: str) -> dict | None: ...

    def write(self, item_type: str, item: dict) -> bool: ...

    def delete(self, item_type: str, id: str) -> bool: ...


# Works — no explicit inheritance required
todos = Inventory(item_type="todo", storage=MyCustomStorage())
```

### Optional explicit inheritance

You can still inherit from the Protocol if you want IDE support for "find all
implementations" or early feedback from a type checker when a method is missing:

```python
from objbase.interface import Storage


class MyCustomStorage(Storage):  # explicit, but optional
  ...
```

### Runtime checks with `isinstance`

Both protocols are `@runtime_checkable`, so you can verify at runtime that an
object has the required methods. This checks method names only, not signatures;
use a type checker for full verification:

```python
from objbase.interface import Storage

isinstance(MyCustomStorage(), Storage)  # True
isinstance("not a storage", Storage)  # False
```

---

## Type Hints

The package ships a `py.typed` marker, so mypy, Pyright and IDEs use its type
hints. The library itself is checked with `mypy --strict`.

- Items are typed as `objbase.Item`, an alias for `dict[str, Any]`.
- `Inventory` and `AsyncInventory` accept and return `Item`; `get` returns `Item | None`.
- `PydanticInventory` and `AsyncPydanticInventory` are generic over their model class, which is inferred from
  `model_class` (see [Pydantic Models](#pydantic-models)).
- Storage adapters accept any structurally compatible client. For example,
  `RedisStorage` takes anything with Redis's `hget`/`hset`/`hdel`/`hvals`
  commands (`redis.Redis`, `redis.asyncio.Redis`, or compatible clients).

---

## Development

See [DEVELOPER.md](DEVELOPER.md)