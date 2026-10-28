from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from psycopg_pool import PoolTimeout
from psycopg.rows import dict_row

from app.core import postgres_pool
from app.core.performance import RequestTimings, request_timings, timed_postgres_connect


def test_all_mappers_share_three_connections_and_fixed_timeouts(monkeypatch):
    made = []
    def create(*args, **kwargs):
        pool = MagicMock(closed=False)
        made.append((args, kwargs, pool))
        return pool
    monkeypatch.setattr(postgres_pool, "ConnectionPool", create)
    monkeypatch.setattr(postgres_pool, "_pools", {})
    first = postgres_pool.get_pool("dbname=test", row_factory=dict_row)
    assert first is postgres_pool.get_pool("dbname=test", row_factory=dict_row)
    assert len(made) == 1
    args, options, _ = made[0]
    assert "connect_timeout=3" in args[0]
    assert options["min_size"] == options["max_size"] == 3
    assert options["timeout"] == 3 and options["max_lifetime"] == 1200
    assert options["max_idle"] == 600
    postgres_pool.close_pools()
    first.close.assert_called_once_with(timeout=3)
    assert postgres_pool.get_pool("dbname=test", row_factory=dict_row) is not first


def test_lease_returns_connections_on_failure_and_does_not_close_raw_connection(monkeypatch):
    raw = MagicMock()
    pool = MagicMock()
    outcomes = []
    @contextmanager
    def lease(**kwargs):
        assert kwargs == {"timeout": 3}
        try:
            yield raw
        except ValueError:
            outcomes.append("rollback-return")
            raise
        else:
            outcomes.append("commit-return")
    pool.connection.side_effect = lease
    monkeypatch.setattr(postgres_pool, "get_pool", lambda *args, **kwargs: pool)
    with pytest.raises(ValueError):
        with timed_postgres_connect("dbname=test"):
            raise ValueError("failed transaction")
    with timed_postgres_connect("dbname=test") as connection:
        assert connection is raw
    assert outcomes == ["rollback-return", "commit-return"]
    raw.close.assert_not_called()


def test_pool_timeout_propagates_and_is_measured(monkeypatch):
    pool = MagicMock()
    pool.connection.return_value.__enter__.side_effect = PoolTimeout("unavailable")
    monkeypatch.setattr(postgres_pool, "get_pool", lambda *args, **kwargs: pool)
    timings = RequestTimings()
    token = request_timings.set(timings)
    try:
        with pytest.raises(PoolTimeout):
            with timed_postgres_connect("dbname=test"):
                pytest.fail("must not continue")
    finally:
        request_timings.reset(token)
    assert timings.values["db_pool_wait"] >= 0
