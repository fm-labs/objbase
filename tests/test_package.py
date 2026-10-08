"""Tests for the package's public surface."""

import subprocess
import sys

import pytest

import objbase


def test_all_names_are_importable():
    for name in objbase.__all__:
        assert getattr(objbase, name) is not None, name


def test_top_level_names_are_the_submodule_objects():
    from objbase.inventory import Inventory
    from objbase.pydantic import AsyncPydanticInventory, PydanticInventory

    assert objbase.Inventory is Inventory
    assert objbase.PydanticInventory is PydanticInventory
    assert objbase.AsyncPydanticInventory is AsyncPydanticInventory


def test_version_is_set():
    assert objbase.__version__ and objbase.__version__ != "0.0.0"


def test_unknown_attribute_raises():
    with pytest.raises(AttributeError, match="DoesNotExist"):
        _ = objbase.DoesNotExist


def test_import_works_without_optional_dependencies():
    """Setting sys.modules[name] = None makes any import of that module fail."""
    code = (
        "import sys\n"
        "for m in ('redis', 'redis.asyncio', 'pymongo', 'pydantic'):\n"
        "    sys.modules[m] = None\n"
        "import objbase\n"
        "inv = objbase.Inventory('todo', objbase.InMemoryStorage())\n"
        "inv.save({'id': '1'})\n"
        "assert inv.get('1') == {'id': '1'}\n"
        "for name in ('PydanticInventory', 'AsyncPydanticInventory'):\n"
        "    try:\n"
        "        getattr(objbase, name)\n"
        "    except ImportError:\n"
        "        print('ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["ok", "ok"]
