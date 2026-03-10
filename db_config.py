"""
Database configuration for Counselling module.
Connects to the shared 'bbtro' MySQL database.
Same pattern as RTIS and SPM apps.

Update credentials to match your server environment.
"""

import mysql.connector
from mysql.connector import pooling
import os

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "jay"),
    "password": os.getenv("DB_PASSWORD", "4310jay"),
    "database": os.getenv("DB_NAME", "bbtro"),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "autocommit": False,
}

# Connection pool for concurrent quiz sessions
_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="runsafe_pool",
            pool_size=10,
            pool_reset_session=True,
            **DB_CONFIG
        )
    return _pool


def get_db_connection():
    """Get a connection from the pool."""
    try:
        return _get_pool().get_connection()
    except Exception:
        # Fallback: direct connection if pool is exhausted
        return mysql.connector.connect(**DB_CONFIG)
