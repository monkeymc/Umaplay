# core/utils/logger.py
from __future__ import annotations
import logging
import sys
import os
from datetime import datetime
from typing import Optional

# ---------- single global logger ----------
logger_uma = logging.getLogger("uma")
logger_uma.propagate = False  # don't bubble to root

# We'll create handlers lazily & idempotently inside setup_uma_logging()
_console: Optional[logging.Handler] = None
_file_handler: Optional[logging.Handler] = None
_file_handler_ts: Optional[logging.Handler] = None  # timestamped file handler


def _has_console_handler(logger: logging.Logger) -> bool:
    return any(
        isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) in (sys.stdout, sys.stderr)
        for h in logger.handlers
    )


def _remove_console_handlers(logger: logging.Logger) -> None:
    for h in list(logger.handlers):
        if isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) in (
            sys.stdout,
            sys.stderr,
        ):
            logger.removeHandler(h)
            try:
                h.close()
            except Exception as e:
                print(f"Error while setting logger: {e}")


def setup_uma_logging(
    debug: bool,
    debug_dir: str = "debug",
    *,
    show_func: bool = False,
    timestamped: bool = True,
) -> None:
    """
    Configure the 'uma' logger (idempotent for notebooks):
    - debug=True  -> console DEBUG; also write debug/debug.log with full paths
    - debug=False -> console ERROR only
    - show_func   -> include function name after the path
    """
    global _console, _file_handler, _file_handler_ts

    # ---- Console handler (filename only) ----
    if _has_console_handler(logger_uma):
        # avoid duplicates when re-running cells
        _remove_console_handlers(logger_uma)

    _console = logging.StreamHandler(sys.stdout)
    func_field = " %(funcName)s()" if show_func else ""
    # ONLY filename + line number on console
    console_fmt = (
        f"%(asctime)s %(levelname)-7s %(filename)s:%(lineno)d{func_field}: %(message)s"
    )
    _console.setFormatter(logging.Formatter(console_fmt, "%H:%M:%S"))
    logger_uma.addHandler(_console)

    # ---- Levels ----
    if debug:
        logger_uma.setLevel(logging.DEBUG)
        _console.setLevel(logging.DEBUG)
    else:
        logger_uma.setLevel(logging.ERROR)
        _console.setLevel(logging.ERROR)

    # ---- File handler (full path) ----
    if debug:
        os.makedirs(debug_dir, exist_ok=True)
        file_fmt = "%(asctime)s %(levelname)-7s %(pathname)s:%(lineno)d %(funcName)s(): %(message)s"
        if _file_handler is None:
            _file_handler = logging.FileHandler(
                os.path.join(debug_dir, "debug.log"), encoding="utf-8"
            )
            _file_handler.setLevel(logging.DEBUG)
            _file_handler.setFormatter(logging.Formatter(file_fmt, "%H:%M:%S"))
            logger_uma.addHandler(_file_handler)
        # Optional per-run timestamped file (idempotent in notebooks)
        if timestamped and _file_handler_ts is None:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
            ts_path = os.path.join(debug_dir, f"debug_{ts}.log")
            _file_handler_ts = logging.FileHandler(ts_path, encoding="utf-8")
            _file_handler_ts.setLevel(logging.DEBUG)
            _file_handler_ts.setFormatter(logging.Formatter(file_fmt, "%H:%M:%S"))
            logger_uma.addHandler(_file_handler_ts)
    else:
        if _file_handler is not None:
            logger_uma.removeHandler(_file_handler)
            try:
                _file_handler.close()
            except Exception as e:
                print(f"Error while setting logger: {e}")
            _file_handler = None
        if _file_handler_ts is not None:
            logger_uma.removeHandler(_file_handler_ts)
            try:
                _file_handler_ts.close()
            except Exception as e:
                print(f"Error while setting logger: {e}")
            _file_handler_ts = None


def get_logger(name=None) -> logging.Logger:
    """Return the global logger or a child (uma.<name>) that shares handlers/levels."""
    if not name or name == "uma":
        return logger_uma
    child = logger_uma.getChild(str(name))
    # children propagate to parent; we don't attach handlers to children
    return child
