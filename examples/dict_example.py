# Simple To-do List Example
from objbase.inventory import Inventory
from objbase.storage.inmemory import InMemoryStorage

# Replace with actual storage instance
todos_inventory = Inventory(item_type="todo", storage=InMemoryStorage())

# Create a new to-do item
new_todo = {"id": "1", "name": "Buy groceries", "status": "pending"}
created_todo = todos_inventory.save(new_todo)
print("Created To-do:", created_todo)

# Read the to-do item
fetched_todo = todos_inventory.get("1")
print("Fetched To-do:", fetched_todo)

# Update the to-do item
updated_todo = todos_inventory.patch("1", {"status": "completed"})
print("Updated To-do:", updated_todo)

# Delete the to-do item
delete_result = todos_inventory.delete("1")
print("Deleted To-do:", delete_result)
