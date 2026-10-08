import asyncio

from objbase.asyncio.inventory import AsyncInventory
from objbase.storage.inmemory import InMemoryStorage


async def main():
    # Replace with AsyncRedisStorage(redis.asyncio.Redis(...)) for real persistence
    todos_inventory = AsyncInventory(item_type="todo", storage=InMemoryStorage())

    # Create a new to-do item
    created_todo = await todos_inventory.save({"id": "1", "name": "Buy groceries", "status": "pending"})
    print("Created To-do:", created_todo)

    # Read the to-do item
    fetched_todo = await todos_inventory.get("1")
    print("Fetched To-do:", fetched_todo)

    # Update the to-do item
    updated_todo = await todos_inventory.patch("1", {"status": "completed"})
    print("Updated To-do:", updated_todo)

    # Delete the to-do item
    delete_result = await todos_inventory.delete("1")
    print("Deleted To-do:", delete_result)


asyncio.run(main())
