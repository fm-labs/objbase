# To-do list backed by MongoDB. Requires `pip install "objbase[mongodb]"` and a running MongoDB,
# e.g. `docker run --rm -p 27017:27017 mongo:7.0`. Set MONGODB_URI to use a different server.
import os

import pymongo

from objbase.collection import Collection
from objbase.interface import Item
from objbase.storage.mongodb import MongoDBStorage

client: pymongo.MongoClient[Item] = pymongo.MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
storage = MongoDBStorage(mongo_client=client)
todos_collection = Collection(item_type="todo", storage=storage)

# Create some to-do items
todos_collection.save({"id": "1", "name": "Buy groceries", "status": "pending"})
todos_collection.save({"id": "2", "name": "Walk the dog", "status": "pending"})
print("All To-dos:", todos_collection.items())

# Update a to-do item
updated_todo = todos_collection.patch("1", {"status": "completed"})
print("Updated To-do:", updated_todo)

# Filter with a MongoDB query (a MongoDB-only extension of the storage adapter)
print("Pending To-dos:", storage.items("todo", query={"status": "pending"}))

# Delete the to-do items
for todo_id in todos_collection.keys():
    print(f"Deleted To-do {todo_id}:", todos_collection.delete(todo_id))

client.close()
