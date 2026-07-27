"""Shared repository plumbing.

Repos open a short session per method rather than sharing one long-lived
session. The bot is a single asyncio process and no operation spans two repos,
so per-method sessions keep things simple without giving up anything.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import async_sessionmaker


class BaseRepo:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory


def one(result: Result) -> Optional[dict[str, Any]]:
    """First row as a plain dict, or None."""
    row = result.mappings().first()
    return dict(row) if row is not None else None


def rows(result: Result) -> list[dict[str, Any]]:
    """All rows as plain dicts."""
    return [dict(r) for r in result.mappings()]
