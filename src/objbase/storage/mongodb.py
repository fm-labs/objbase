from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from objbase.interface import Item, Storage

if TYPE_CHECKING:
    from pymongo import MongoClient
    from pymongo.collection import Collection


class MongoDBStorage(Storage):
    """MongoDB-based storage implementation for inventory items."""

    def __init__(self, mongo_client: "MongoClient[Item]"):
        self.mongo_client = mongo_client

    def get_mongo_collection(self, item_type: str) -> "Collection[Item]":
        db = self.mongo_client["inventory"]
        return db[item_type]

    def keys(self, item_type: str) -> list[str]:
        collection = self.get_mongo_collection(item_type)
        return [doc["id"] for doc in collection.find({}, {"id": True, "_id": False})]

    def items(self, item_type: str, query: Mapping[str, Any] | None = None) -> list[Item]:
        """Return all items of a type. ``query`` is a MongoDB-only extension to filter results."""
        collection = self.get_mongo_collection(item_type)
        return list(collection.find(query or {}, {"_id": False}))

    def write(self, item_type: str, item: Item) -> bool:
        collection = self.get_mongo_collection(item_type)
        collection.replace_one({"id": item["id"]}, item, upsert=True)
        return True

    def read(self, item_type: str, id: str) -> Item | None:
        collection = self.get_mongo_collection(item_type)
        return collection.find_one({"id": id}, {"_id": False})

    def delete(self, item_type: str, id: str) -> bool:
        collection = self.get_mongo_collection(item_type)
        result = collection.delete_one({"id": id})
        return result.deleted_count > 0
