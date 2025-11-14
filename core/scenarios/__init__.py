from __future__ import annotations

from .registry import registry

# Import scenario modules to trigger registry registration
from . import ura  # noqa: F401
from . import unity_cup  # noqa: F401

__all__ = ["registry"]
