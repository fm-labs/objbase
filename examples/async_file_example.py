# Async to-do list stored in one JSON file per item type ({base_dir}/todo.json). No extra dependencies needed.
# Set OBJBASE_DATA_DIR to use a different directory.
import asyncio
import os

from objbase.asyncio.collection import AsyncCollection
from objbase.asyncio.storage.local import AsyncLocalFileStorage


async def main() -> None:
    base_dir = os.getenv("OBJBASE_DATA_DIR", "data")
    os.makedirs(base_dir, exist_ok=True)  # the base directory must exist
    storage = AsyncLocalFileStorage(base_dir=base_dir)
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
