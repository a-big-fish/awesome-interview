"""Small process-wide PostgreSQL pool shared by all metadata mappers."""

import atexit
from contextlib import contextmanager
from threading import Lock

from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

_pools: dict[tuple, ConnectionPool] = {}
_lock = Lock()


def get_pool(conninfo: str, **kwargs) -> ConnectionPool:
    # Physical connection establishment and pool acquisition both fail within 3s.
    conninfo = make_conninfo(conninfo, connect_timeout=3)
    key = (conninfo, tuple(sorted(kwargs.items())))
    with _lock:
        pool = _pools.get(key)
        if pool is None or pool.closed:
            pool = ConnectionPool(conninfo, kwargs=kwargs, min_size=3, max_size=3,
                                  timeout=3, max_lifetime=20 * 60, max_idle=10 * 60,
                                  open=True, name="metadata")
            _pools[key] = pool
        return pool


@contextmanager
def connection(conninfo: str, **kwargs):
    from app.core.performance import _TimedDatabase, measure_phase, request_timings
    scope = get_pool(conninfo, **kwargs).connection(timeout=3)
    with measure_phase("db_pool_wait"):
        raw = scope.__enter__()
    try:
        yield _TimedDatabase(raw) if request_timings.get() is not None else raw
    except BaseException:
        import sys
        with measure_phase("db_query"):
            suppressed = scope.__exit__(*sys.exc_info())
        if not suppressed:
            raise
    else:
        with measure_phase("db_query"):
            scope.__exit__(None, None, None)


def close_pools() -> None:
    with _lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.close(timeout=3)


atexit.register(close_pools)
