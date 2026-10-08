class CollectionError(Exception):
    """Base class for all objbase errors."""


class ItemNotFoundError(CollectionError, LookupError):
    """Raised when an operation requires an item that does not exist."""

    def __init__(self, item_type: str, id: str):
        self.item_type = item_type
        self.id = id
        super().__init__(f"Item '{id}' of type '{item_type}' not found.")
