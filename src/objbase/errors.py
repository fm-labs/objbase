class CollectionError(Exception):
    """Base class for all objbase errors."""


class ItemNotFoundError(CollectionError, LookupError):
    """Raised when an operation requires an item that does not exist."""

    def __init__(self, item_type: str, id: str):
        self.item_type = item_type
        self.id = id
        super().__init__(f"Item '{id}' of type '{item_type}' not found.")


class ActionNotFoundError(CollectionError, LookupError):
    """Raised when an action is not registered on a collection or not found in a module."""

    def __init__(self, action: str, source: str):
        self.action = action
        self.source = source
        super().__init__(f"Action '{action}' not found for {source}.")
