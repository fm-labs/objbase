# Async to-do list backed by SQLite. No extra dependencies needed.
# Set SQLITE_DB_PATH to use a different database file.
import asyncio
import os

from objbase.asyncio.collection import AsyncCollection
from objbase.asyncio.storage.sqlite import AsyncSQLiteStorage


async def main() -> None:
    db_path = os.getenv("SQLITE_DB_PATH", os.path.join("data", "todos.db"))
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)  # sqlite3 doesn't create missing directories
    storage = AsyncSQLiteStorage(db_path=db_path)
    todos_collection = AsyncCollection(item_type="todo", storage=storage)

    # Create some to-do items
    await todos_collection.save({"id": "1", "name": "Buy groceries", "status": "pending"})
    await todos_collection.save({"id": "2", "name": "Walk the dog", "status": "pending"})
    print("All To-dos:", await todos_collection.items())

    # Update a to-do item
    updated_todo = await todos_collection.patch("1", {"status": "completed"})
    print("Updated To-do:", updated_todo)

    # Delete the to-do items
    for todo_id in await todos_collection.keys():
        print(f"Deleted To-do {todo_id}:", await todos_collection.delete(todo_id))


asyncio.run(main())
