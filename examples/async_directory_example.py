# Async to-do list stored in one JSON file per item ({base_dir}/todo/{id}.json). No extra dependencies needed.
# Set INVENTORY_DIR to use a different directory.
import asyncio
import os

from objbase.asyncio.inventory import AsyncInventory
from objbase.asyncio.storage.local import AsyncLocalDirectoryStorage


async def main() -> None:
    base_dir = os.getenv("INVENTORY_DIR", "data")
    os.makedirs(base_dir, exist_ok=True)  # the base directory must exist
    storage = AsyncLocalDirectoryStorage(base_dir=base_dir)
    todos_inventory = AsyncInventory(item_type="todo", storage=storage)

    # Create some to-do items concurrently; the adapter's file locks keep the index consistent
    await asyncio.gather(
        todos_inventory.save({"id": "1", "name": "Buy groceries", "status": "pending"}),
        todos_inventory.save({"id": "2", "name": "Walk the dog", "status": "pending"}),
    )
    print("To-do ids:", sorted(await todos_inventory.keys()))

    # Update a to-do item
    updated_todo = await todos_inventory.patch("1", {"status": "completed"})
    print("Updated To-do:", updated_todo)

    # Rebuild the index, e.g. after item files were added or removed by hand
    await storage.arebuild_index("todo")

    # Delete the to-do items
    for todo_id in await todos_inventory.keys():
        print(f"Deleted To-do {todo_id}:", await todos_inventory.delete(todo_id))


asyncio.run(main())
