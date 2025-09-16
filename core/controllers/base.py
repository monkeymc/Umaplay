# core/controllers/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from PIL import Image

Point = Tuple[int, int]
RegionXYWH = Tuple[int, int, int, int]  # (left, top, width, height)

class IController(ABC):
    """Abstract device/window controller."""

    @abstractmethod
    def focus(self) -> bool: ...

    @abstractmethod
    def screenshot(self, region: Optional[RegionXYWH] = None) -> Image.Image: ...

    @abstractmethod
    def move_to(self, x: int, y: int, duration: float = 0.15) -> None: ...

    @abstractmethod
    def click(self, x: int, y: int, clicks: int = 1, duration: float = 0.15) -> None: ...

    @abstractmethod
    def scroll(self, amount: int) -> None: ...  # negative = down

    @abstractmethod
    def resolution(self) -> Tuple[int, int]: ...

    @abstractmethod
    def capture_origin(self) -> Tuple[int, int]: ...
