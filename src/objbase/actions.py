"""Action handlers: named operations registered on a collection and run against one item.

A handler takes the stored item and the action parameters, and returns either the
updated item, which the collection saves, or ``None`` to leave the item unchanged.
"""

import importlib
from collections.abc import Awaitable, Callable
from typing import Any

from objbase.errors import ActionNotFoundError
from objbase.interface import Item

ActionParams = dict[str, Any]
"""Parameters passed to an action handler."""

ActionHandler = Callable[[Item, ActionParams], Item | None]
"""A sync action handler: ``handler(item, params) -> updated item | None``."""

AsyncActionHandler = Callable[[Item, ActionParams], Awaitable[Item | None]]
"""An async action handler: ``async handler(item, params) -> updated item | None``."""


def check_action_name(name: str) -> None:
    """Raise ``ValueError`` if ``name`` is not a usable action name."""
    if not name or not isinstance(name, str):
        raise ValueError("Action name must be a non-empty string.")


def check_action_result(id: str, result: Item) -> None:
    """Raise ``ValueError`` if a handler's returned item does not keep the item id."""
    if result.get("id") != id:
        raise ValueError("Action handler must return the item with its id unchanged.")


def load_action_handler(module_name: str, action_name: str, attr_name: str = "actions") -> Callable[..., Any]:
    """Import ``module_name`` and return ``getattr(module, attr_name)[action_name]``.

    The module must define a mapping of action names to handlers (``actions`` by default).
    The returned handler can be passed to ``register_action``.

    Errors raised while importing the module (``ImportError`` or any error in the
    module itself) propagate unchanged.

    :raises ActionNotFoundError: If the module has no such mapping or the mapping has no such action.
    :raises TypeError: If the mapping entry is not callable.
    """
    module = importlib.import_module(module_name)
    actions = getattr(module, attr_name, None)
    if actions is None or action_name not in actions:
        raise ActionNotFoundError(action_name, f"module '{module_name}' ({attr_name})")
    handler = actions[action_name]
    if not callable(handler):
        raise TypeError(f"Action '{action_name}' in module '{module_name}' is not callable.")
    return handler  # type: ignore[no-any-return]
