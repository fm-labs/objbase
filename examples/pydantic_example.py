import pydantic

from objbase.pydantic import PydanticCollection
from objbase.storage.inmemory import InMemoryStorage


class Todo(pydantic.BaseModel):
    id: str
    title: str
    completed: bool = False


model_storage = InMemoryStorage()
todos_inventory = PydanticCollection(item_type="todos", model_class=Todo, storage=model_storage)

# Create a new to-do item
created_todo = todos_inventory.save(Todo(id="1", title="Buy milk", completed=False))
print("Created To-do:", created_todo)

# Read the to-do item
fetched_todo = todos_inventory.get("1")
print("Fetched To-do:", fetched_todo)
assert fetched_todo is not None  # get() returns None for a missing id

# Update the to-do item
fetched_todo.completed = True
updated_todo = todos_inventory.patch("1", fetched_todo)
print("Updated To-do:", updated_todo)

# Delete the to-do item
delete_result = todos_inventory.delete("1")
print("Deleted To-do:", delete_result)
