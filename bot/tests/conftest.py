"""
Pytest fixtures.

If TEST_DATABASE_URL (or DATABASE_URL) is set and points to a reachable
PostgreSQL instance, integration tests run. Otherwise they are skipped.

The test schema is created in a separate `chatochi_test` database so that
the developer's local database isn't polluted.
"""
import os
import sys
import uuid

import pytest


# Make the bot package importable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _check_pg(url: str) -> bool:
    try:
        import psycopg2  # noqa
        conn = psycopg2.connect(url, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


PG_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL", "")
PG_AVAILABLE = bool(PG_URL) and _check_pg(PG_URL)


@pytest.fixture(scope="session")
def test_db_url() -> str:
    if not PG_AVAILABLE:
        pytest.skip("PostgreSQL not available — set TEST_DATABASE_URL to enable DB tests", allow_module_level=False)
    return PG_URL


@pytest.fixture
def fresh_db(test_db_url):
    """Per-test Database with all tables (re)created on a random suffix
    of table names so concurrent test runs don't collide."""
    if not PG_AVAILABLE:
        pytest.skip("PostgreSQL not available")
    from database.db import Database
    db = Database(test_db_url)
    # create a unique schema namespace for this test run
    schema = "t_" + uuid.uuid4().hex[:12]
    with db._cursor(autocommit=True) as (conn, cur):
        cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        cur.execute(f"CREATE SCHEMA {schema}")
        # set search path on this connection
        cur.execute(f"SET search_path TO {schema}")
    # now create tables
    db.create_tables()
    yield db
    # cleanup
    try:
        with db._cursor(autocommit=True) as (conn, cur):
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    except Exception:
        pass
    db.close()
