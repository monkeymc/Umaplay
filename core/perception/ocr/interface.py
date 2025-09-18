# core/perception/ocr/interface.py
from __future__ import annotations
from typing import Any, Dict, List, Protocol, runtime_checkable

@runtime_checkable
class OCRInterface(Protocol):
    """
    Interface for OCR engines.
    Implementations may be local (Paddle) or remote (HTTP).
    """

    def raw(self, img: Any) -> Dict[str, Any]:
        """Return a normalized JSON-like dict (e.g., PaddleOCR _to_json())."""

    def text(self, img: Any, joiner: str = " ", min_conf: float = 0.2) -> str:
        """Return a whitespace-joined string of recognized text above min_conf."""

    def digits(self, img: Any) -> int:
        """Return only the digits as an int (or -1 if none/parse failure)."""

    def batch_text(self, imgs: List[Any], *, joiner: str = " ", min_conf: float = 0.2) -> List[str]:
        """Vectorized text() over a list of images."""

    def batch_digits(self, imgs: List[Any]) -> List[str]:
        """Vectorized digits-only strings for each image."""
