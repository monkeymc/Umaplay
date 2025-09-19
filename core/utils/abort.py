import threading

_ABORT = threading.Event()

def request_abort() -> None:
    """Set the global abort flag (cooperative hard stop)."""
    _ABORT.set()

def clear_abort() -> None:
    """Clear the global abort flag."""
    _ABORT.clear()

def abort_requested() -> bool:
    """Check if an abort has been requested."""
    return _ABORT.is_set()