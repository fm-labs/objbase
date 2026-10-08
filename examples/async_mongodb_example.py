# Async to-do list backed by MongoDB. Requires `pip install "objbase[mongodb]"` and a running MongoDB,
# e.g. `docker run --rm -p 27017:27017 mongo:7.0`. Set MONGODB_URI to use a different server.
import asyncio
import os

import pymongo

from objbase.asyncio.collection import AsyncCollection
from objbase.asyncio.storage.mongodb import AsyncMongoDBStorage
from objbase.interface import Item


async def main() -> None:
    client: pymongo.AsyncMongoClient[Item] = pymongo.AsyncMongoClient(
        os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    )
    storage = AsyncMongoDBStorage(mongo_client=client)
    todos_collection = AsyncCollection(item_type="todo", storage=storage)

    # Create some to-do items
    await todos_collection.save({"id": "1", "name": "Buy groceries", "status": "pending"})
    await todos_collection.save({"id": "2", "name": "Walk the dog", "status": "pending"})
    print("All To-dos:", await todos_collection.items())

    # Update a to-do item
    updated_todo = await todos_collection.patch("1", {"status": "completed"})
    print("Updated To-do:", updated_todo)

    # Filter with a MongoDB query (a MongoDB-only extension of the storage adapter)
    print("Pending To-dos:", await storage.aitems("todo", query={"status": "pending"}))

    # Delete the to-do items
    for todo_id in await todos_collection.keys():
        print(f"Deleted To-do {todo_id}:", await todos_collection.delete(todo_id))

    await client.close()


asyncio.run(main())
