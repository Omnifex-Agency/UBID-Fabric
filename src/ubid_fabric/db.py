"""
UBID Fabric — Database Connection Pool
Manages PostgreSQL and Redis connections.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
import redis.asyncio as aioredis
import redis as sync_redis
import structlog

from ubid_fabric.config import settings

logger = structlog.get_logger()

# ─── PostgreSQL ──────────────────────────────────────────────

_pg_pool: ConnectionPool | None = None


def get_pg_pool() -> ConnectionPool:
    """Get or create the PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = ConnectionPool(
            settings.database_url,
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row},
        )
        logger.info("pg_pool_created", url=settings.database_url.split("@")[-1])
    return _pg_pool


def get_pg_connection():
    """Get a connection from the pool (use as context manager)."""
    return get_pg_pool().connection()


# ─── Redis ───────────────────────────────────────────────────

_redis_client: sync_redis.Redis | None = None


def get_redis() -> sync_redis.Redis:
    """Get or create the Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = sync_redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        logger.info("redis_connected", url=settings.redis_url)
    return _redis_client


# ─── Cleanup ─────────────────────────────────────────────────

def close_all():
    """Close all connections (call on shutdown)."""
    global _pg_pool, _redis_client
    if _pg_pool:
        _pg_pool.close()
        _pg_pool = None
    if _redis_client:
        _redis_client.close()
        _redis_client = None
    logger.info("connections_closed")
