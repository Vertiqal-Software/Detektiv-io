from __future__ import annotations
from typing import Any, Generator
from app.core.session import get_db as core_get_db

def get_db() -> Generator[Any, None, None]:
    # Tests usually override this; if not, the core stub raises to avoid accidental usage.
    yield from core_get_db()

__all__ = ["get_db"]
