import asyncio

import pydantic

from objbase.pydantic import AsyncPydanticCollection
from objbase.storage.inmemory import InMemoryStorage


class Todo(pydantic.BaseModel):
    id: str
    title: str
    completed: bool = False


async def main() -> None:
    # Replace with AsyncRedisStorage(redis.asyncio.Redis(...)) for real persistence
    todos_inventory = AsyncPydanticCollection(item_type="todos", storage=InMemoryStorage(), model_class=Todo)

    # Create a new to-do item
    created_todo = await todos_inventory.save(Todo(id="1", title="Buy milk"))
    print("Created To-do:", created_todo)

    # Read the to-do item
    fetched_todo = await todos_inventory.get("1")
    print("Fetched To-do:", fetched_todo)
    assert fetched_todo is not None  # get() returns None for a missing id

    # Update the to-do item
    fetched_todo.completed = True
    updated_todo = await todos_inventory.patch("1", fetched_todo)
    print("Updated To-do:", updated_todo)

    # Invalid data is rejected and never stored
    try:
        await todos_inventory.patch("1", {"completed": "not a bool"})
    except pydantic.ValidationError:
        print("Rejected invalid patch; stored item unchanged:", await todos_inventory.get("1"))

    # Delete the to-do item
    delete_result = await todos_inventory.delete("1")
    print("Deleted To-do:", delete_result)


asyncio.run(main())
