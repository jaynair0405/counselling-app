"""
Database Connection Configuration
Handles MySQL connection pooling and configuration
"""
import os
from typing import Optional
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database configuration from environment
DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE", "bbtro"),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "autocommit": False,
}

# Connection pool (initialized when needed)
_pool: Optional[pooling.MySQLConnectionPool] = None


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


def test_connection() -> bool:
    """Test database connectivity"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS test")
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if result and result[0] == 1:
            print("[DB] ✓ Connection test successful!")
            return True
        else:
            print("[DB] ✗ Connection test returned unexpected result")
            return False
    except mysql.connector.Error as e:
        print(f"[DB] ✗ Connection test failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing MySQL connection...")
    print(f"Host: {DB_CONFIG['host']}")
    print(f"Port: {DB_CONFIG['port']}")
    print(f"Database: {DB_CONFIG['database']}")
    print(f"User: {DB_CONFIG['user']}")
    print()

    if test_connection():
        print("\n✓ Database configuration is correct!")
    else:
        print("\n✗ Database connection failed!")
