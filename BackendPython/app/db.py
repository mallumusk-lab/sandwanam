"""Connection pool. Created lazily per event loop: serverless runtimes may not run
lifespan hooks, and a pool must never be shared across event loops."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

import asyncpg

from .config import settings
from .errors import ServiceUnavailable
from .repositories import Repos

_pool: asyncpg.Pool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None
_lock: asyncio.Lock | None = None
_lock_loop: asyncio.AbstractEventLoop | None = None


async def pool() -> asyncpg.Pool:
    global _pool, _pool_loop, _lock, _lock_loop
    loop = asyncio.get_running_loop()
    if _pool is not None and _pool_loop is loop:
        return _pool
    if _lock is None or _lock_loop is not loop:
        _lock, _lock_loop = asyncio.Lock(), loop
    async with _lock:
        if _pool is not None and _pool_loop is loop:
            return _pool
        if _pool is not None:  # created on an event loop that is gone
            try:
                _pool.terminate()
            except Exception:  # its loop may already be closed; the connections die with it
                pass
            _pool, _pool_loop = None, None
        url = settings().database_url
        if not url:
            raise ServiceUnavailable("The database is not configured.", code="database_unconfigured")
        try:
            _pool = await asyncpg.create_pool(
                url,
                min_size=0,
                max_size=5,
                statement_cache_size=0,  # required behind Supabase's transaction pooler
                command_timeout=30,
                max_inactive_connection_lifetime=60,
            )
        except (OSError, asyncpg.PostgresError) as exc:
            raise ServiceUnavailable("The database is unavailable. Try again shortly.", code="database_unavailable") from exc
        _pool_loop = loop
        return _pool


async def close() -> None:
    global _pool, _pool_loop
    if _pool is not None:
        await _pool.close()
    _pool, _pool_loop = None, None


async def repos() -> AsyncIterator[Repos]:
    """FastAPI dependency: one pooled connection per request."""
    current = await pool()
    try:
        connection = await current.acquire(timeout=10)
    except (OSError, asyncio.TimeoutError, asyncpg.PostgresError) as exc:
        raise ServiceUnavailable("The database is busy. Try again shortly.", code="database_unavailable") from exc
    try:
        yield Repos(connection)
    finally:
        await current.release(connection)
