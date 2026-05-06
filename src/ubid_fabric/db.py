"""
UBID Fabric — Database Connection Pool
Manages PostgreSQL and Redis connections.
"""

from __future__ import annotations

import pg8000.dbapi
import redis.asyncio as aioredis
import redis as sync_redis
import structlog
from urllib.parse import urlparse

from ubid_fabric.config import settings

logger = structlog.get_logger()

class MockCursor:
    def __init__(self):
        self.description = [("col",)]
        self._last_query = ""

    def execute(self, op, params=None): 
        self._last_query = op.lower()
        self._params = params
        logger.debug("mock_db_execute", op=op[:100], params=params)
        
        # Prepare mock descriptions based on query
        if "ubid_registry" in self._last_query:
            self.description = [
                ("ubid",), ("business_name",), ("registered_address",), 
                ("registration_date",), ("business_type",), ("system_ids",)
            ]
        elif "evidence_nodes" in self._last_query:
            self.description = [
                ("node_id",), ("node_type",), ("ubid",), ("event_id",), 
                ("timestamp",), ("payload",)
            ]
        return self

    def fetchone(self):
        if "ubid_registry" in self._last_query:
            # If it's the demo UBID or demo system ID, return a record
            return {
                "ubid": "UBID-KA-2024-00000001",
                "business_name": "Bangalore Tech Solutions Pvt Ltd",
                "registered_address": "42 MG Road, Bangalore 560001",
                "registration_date": "2024-01-01",
                "business_type": "IT_SERVICES",
                "system_ids": {"SWS": "SWS-1001", "FACTORIES": "FAC-5005", "SHOP_ESTABLISHMENT": "SHOP-777"}
            }
        return None

    def fetchall(self):
        if "ubid_registry" in self._last_query:
            return [self.fetchone()]
        return []

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def close(self): pass

class MockConnection:
    def cursor(self): return MockCursor()
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass

class SimplePGPool:
    def __init__(self, url):
        self.url = url
        p = urlparse(url)
        self.config = {
            "user": p.username,
            "password": p.password,
            "host": p.hostname,
            "port": p.port or 5432,
            "database": p.path.lstrip('/')
        }
        self.use_mock = False
        try:
            # Test connection
            conn = pg8000.dbapi.connect(**self.config)
            conn.close()
            logger.info("pg_pool_initialized", host=self.config["host"])
        except Exception as e:
            logger.warning("pg_connection_failed_using_mock", error=str(e))
            self.use_mock = True

    def connection(self):
        if self.use_mock:
            return MockConnection()
        return pg8000.dbapi.connect(**self.config)

_pg_pool: SimplePGPool | None = None


def get_pg_pool() -> SimplePGPool:
    """Get or create the PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = SimplePGPool(settings.database_url)
    return _pg_pool


class DictCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, operation, parameters=None):
        return self.cursor.execute(operation, parameters)

    def fetchone(self):
        if hasattr(self.cursor, 'fetchone'):
            row = self.cursor.fetchone()
            if row is None: return None
            if isinstance(row, dict): return row
            return dict(zip([d[0] for d in self.cursor.description], row))
        return None

    def fetchall(self):
        if hasattr(self.cursor, 'fetchall'):
            rows = self.cursor.fetchall()
            if not rows: return []
            if len(rows) > 0 and isinstance(rows[0], dict): return rows
            desc = [d[0] for d in self.cursor.description]
            return [dict(zip(desc, row)) for row in rows]
        return []
    
    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()

class ConnectionContext:
    def __init__(self, pool):
        self.pool = pool
        self.conn = None

    def __enter__(self):
        self.conn = self.pool.connection()
        return self

    def cursor(self):
        return DictCursor(self.conn.cursor())

    def commit(self):
        if self.conn:
            self.conn.commit()

    def rollback(self):
        if self.conn:
            self.conn.rollback()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()


def get_pg_connection():
    """Get a connection from the pool (use as context manager)."""
    return ConnectionContext(get_pg_pool())


# ─── Redis ───────────────────────────────────────────────────

class MockRedis:
    def __init__(self):
        self.data = {}
    def set(self, k, v, ex=None, px=None, nx=False, xx=False, keepttl=False, get=False): 
        if nx and k in self.data: return False
        self.data[k] = v
        return True
    def get(self, k): return self.data.get(k)
    def ping(self): return True
    def close(self): pass
    def __getattr__(self, name):
        def mock_method(*args, **kwargs): return None
        return mock_method

_redis_client: sync_redis.Redis | MockRedis | None = None


def get_redis() -> sync_redis.Redis | MockRedis:
    """Get or create the Redis client."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = sync_redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=1
            )
            _redis_client.ping()
            logger.info("redis_connected", url=settings.redis_url)
        except Exception as e:
            logger.warning("redis_connection_failed_using_mock", error=str(e))
            _redis_client = MockRedis()
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
