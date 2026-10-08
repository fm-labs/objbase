from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from objbase.interface import AsyncStorage, Item

if TYPE_CHECKING:
    from pymongo import AsyncMongoClient
    from pymongo.asynchronous.collection import AsyncCollection


class AsyncMongoDBStorage(AsyncStorage):
    """Async counterpart of ``MongoDBStorage``, using the same data layout.

    Takes an async client such as ``pymongo.AsyncMongoClient``.
    """

    def __init__(self, mongo_client: "AsyncMongoClient[Item]"):
        self.mongo_client = mongo_client

    def get_mongo_collection(self, item_type: str) -> "AsyncCollection[Item]":
        db = self.mongo_client["collection"]
        return db[item_type]

    async def akeys(self, item_type: str) -> list[str]:
        collection = self.get_mongo_collection(item_type)
        return [doc["id"] async for doc in collection.find({}, {"id": True, "_id": False})]

    async def aitems(self, item_type: str, query: Mapping[str, Any] | None = None) -> list[Item]:
        """Return all items of a type. ``query`` is a MongoDB-only extension to filter results."""
        collection = self.get_mongo_collection(item_type)
        return [doc async for doc in collection.find(query or {}, {"_id": False})]

    async def awrite(self, item_type: str, item: Item) -> bool:
        collection = self.get_mongo_collection(item_type)
        await collection.replace_one({"id": item["id"]}, item, upsert=True)
        return True

    async def aread(self, item_type: str, id: str) -> Item | None:
        collection = self.get_mongo_collection(item_type)
        return await collection.find_one({"id": id}, {"_id": False})

    async def adelete(self, item_type: str, id: str) -> bool:
        collection = self.get_mongo_collection(item_type)
        result = await collection.delete_one({"id": id})
        return result.deleted_count > 0
