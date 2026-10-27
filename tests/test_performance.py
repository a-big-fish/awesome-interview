"""Performance collection stays bounded, anonymous, asynchronous and admin-only."""

import json
import sqlite3
import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.performance import RequestTimings, node_for_path, request_timings, timed_postgres_connect
from app.model.auth import AuthUser
from app.service.auth_service import hash_password
from app.service.performance_service import PerformanceService
from app.controller.schema.performance_dto import PerformanceBatch
from pydantic import ValidationError
from tests.test_public_multiuser import _login, _public_fixture


def test_async_storage_persists_distributions_and_prunes_old_samples(tmp_path):
    path = tmp_path / "performance.sqlite3"
    store = PerformanceService(path)
    for duration in (10, 100, 1000, 2000):
        store.record("calendar", "server", "request", duration, 500 if duration == 2000 else 200)
    store.record("calendar", "browser", "request", 1200, 0)
    store.record("editor", "browser", "longtask", 300)
    assert not path.exists()  # record() performs no filesystem I/O.
    store.start()
    store.stop()
    snapshot = store.dashboard()
    assert snapshot["server_count"] == 4 and snapshot["browser_count"] == 1
    assert snapshot["errors"] == 1 and snapshot["longtasks"] == 1
    group = next(row for row in snapshot["groups"] if row["source"] == "server")
    assert (group["p50"], group["p95"]) == (100, 2000)
    assert len(snapshot["trend"]) == 24
    with sqlite3.connect(path) as connection:
        assert [row[1] for row in connection.execute("PRAGMA table_info(samples)")] == [
            "id", "received", "node", "source", "metric", "duration", "status"]
        connection.execute("INSERT INTO samples(received,node,source,metric,duration,status) VALUES(?,?,?,?,?,?)",
                           (time.time() - 8 * 86400, "calendar", "server", "request", 10, 200))
    restarted = PerformanceService(path)
    restarted.start()
    deadline = time.monotonic() + 2
    while not restarted.ready and time.monotonic() < deadline:
        time.sleep(.01)
    restarted.stop()
    assert restarted.dashboard()["server_count"] == 4
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 6


def test_full_queue_and_broken_storage_do_not_raise_into_business_requests(tmp_path):
    invalid_path = tmp_path / "not-a-directory"
    invalid_path.write_text("occupied")
    store = PerformanceService(invalid_path / "performance.sqlite3")
    for _ in range(2001):
        store.record("calendar", "server", "request", 10)
    assert store.queue.qsize() == 2000 and store.dropped == 1
    store.start()
    deadline = time.monotonic() + 2
    while not store.write_failures and time.monotonic() < deadline:
        time.sleep(.01)
    store.stop()
    assert not store.dashboard()["ready"] and store.write_failures > 0


def test_empty_performance_dashboard_has_an_explicit_healthy_empty_state(tmp_path):
    store = PerformanceService(tmp_path / "empty.sqlite3")
    store.start()
    deadline = time.monotonic() + 2
    while not store.ready and time.monotonic() < deadline:
        time.sleep(.01)
    store.stop()
    result = store.dashboard()
    assert result["ready"] and result["groups"] == [] and result["slow"] == []
    assert result["server_count"] == result["browser_count"] == 0
    assert all(row["count"] == 0 for row in result["trend"])


@pytest.mark.parametrize("path,method,node", [
    ("/my-schedule/experiences/private-id/export.pdf?title=secret", "GET", "pdf"),
    ("/my-schedule/experiences/private-id/draft", "POST", "draft"),
    ("/my-schedule/experiences/private-id/parse-file", "POST", "parse"),
    ("/my-schedule/events/private-id/completion", "POST", "event_write"),
    ("/my-schedule/admin/performance", "GET", None),
    ("/my-schedule/telemetry", "POST", None),
    ("/static/logo.png", "GET", None),
])
def test_nodes_never_retain_resource_ids_or_query_parameters(path, method, node):
    assert node_for_path(path, method) == node


def test_database_phases_include_failed_queries_without_retaining_sql(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value = cursor
    cursor.execute.side_effect = RuntimeError("failed query")
    monkeypatch.setattr("app.core.performance.psycopg.connect", lambda *args, **kwargs: connection)
    timings = RequestTimings()
    token = request_timings.set(timings)
    try:
        with timed_postgres_connect("not-a-real-dsn") as timed:
            with timed.cursor() as query:
                with pytest.raises(RuntimeError):
                    query.execute("private sql", ["private parameters"])
    finally:
        request_timings.reset(token)
    assert set(timings.values) == {"db_connect", "db_query"}
    assert all(duration >= 0 for duration in timings.values.values())


def test_performance_ingestion_permissions_validation_and_no_self_collection(tmp_path):
    app, mapper, _, _, _, _ = _public_fixture(tmp_path)
    ordinary = AuthUser(email="metrics@example.com", password_hash=hash_password("test-password"), email_verified=True)
    admin = AuthUser(username="metrics-admin", password_hash=hash_password("test-password"),
                     email_verified=True, is_admin=True)
    mapper.create_user(ordinary)
    mapper.create_user(admin)
    payload = json.dumps({"samples": [{"node": "calendar", "metric": "request", "duration": 1234.5, "status": 200}]})
    with TestClient(app, base_url="https://testserver") as client:
        assert 'name="performance-csrf"' not in client.get("/auth/login").text
        assert client.get("/my-schedule/admin/performance", follow_redirects=False).status_code == 303
        assert client.post("/my-schedule/telemetry", data={"payload": payload}).status_code == 401
        csrf = _login(client, ordinary.email, "test-password")
        assert client.get("/my-schedule/admin/performance").status_code == 403
        assert client.post("/my-schedule/telemetry", data={"payload": payload}).status_code == 403
        assert client.post("/my-schedule/telemetry", data={"csrf_token": csrf, "payload": payload}).status_code == 204
        invalid = json.dumps({"samples": [{"node": "/secret-account", "metric": "request", "duration": 10}]})
        response = client.post("/my-schedule/telemetry", data={"csrf_token": csrf, "payload": invalid})
        assert response.status_code == 422 and "secret-account" not in response.text
        oversized = json.dumps({"samples": [{"node": "calendar", "metric": "request", "duration": 10}] * 21})
        assert client.post("/my-schedule/telemetry", data={"csrf_token": csrf, "payload": oversized}).status_code == 422
        assert client.post("/my-schedule/telemetry", data={"csrf_token": csrf, "payload": "x" * 12001}).status_code == 413
        client.cookies.clear()
        _login(client, "metrics-admin", "test-password")
        assert client.get("/my-schedule/admin").status_code == 200
        assert client.get("/my-schedule/admin/performance?hours=2").status_code == 422
        assert client.get("/my-schedule/admin/performance").status_code == 200
        calendar = client.get("/my-schedule")
        assert "app;dur=" in calendar.headers["server-timing"]
        assert "auth;dur=" in calendar.headers["server-timing"]
    stored = app.state.performance.dashboard()
    assert any(row["source"] == "browser" and row["p95"] == 1234.5 for row in stored["groups"])
    assert all(row["node"] not in {"admin", "telemetry"} for row in stored["groups"])
    assert ordinary.email not in json.dumps(stored) and ordinary.id not in json.dumps(stored)


def test_disabled_performance_does_not_create_files(tmp_path):
    app, mapper, _, _, _, _ = _public_fixture(tmp_path)
    app.state.performance.enabled = False
    app.state.settings.performance_enabled = False
    user = AuthUser(email="disabled@example.com", password_hash=hash_password("test-password"), email_verified=True)
    mapper.create_user(user)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client, user.email, "test-password")
        assert 'name="performance-csrf"' not in client.get("/my-schedule/new").text
    assert not app.state.performance.path.exists()


def test_performance_batches_are_rate_limited(tmp_path):
    app, mapper, _, _, _, _ = _public_fixture(tmp_path)
    user = AuthUser(email="rate@example.com", password_hash=hash_password("test-password"), email_verified=True)
    mapper.create_user(user)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client, user.email, "test-password")
        data = {"csrf_token": csrf, "payload": json.dumps({"samples": [
            {"node": "calendar", "metric": "request", "duration": 10}]})}
        for _ in range(30):
            assert client.post("/my-schedule/telemetry", data=data).status_code == 204
        response = client.post("/my-schedule/telemetry", data=data)
        assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_unhandled_business_failure_still_records_a_failed_server_sample(tmp_path):
    from app.core.dependencies import get_personal_schedule_service
    app, mapper, _, _, _, _ = _public_fixture(tmp_path)
    user = AuthUser(email="failure@example.com", password_hash=hash_password("test-password"), email_verified=True)
    mapper.create_user(user)

    def unavailable():
        raise RuntimeError("backend unavailable")

    app.dependency_overrides[get_personal_schedule_service] = unavailable
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as client:
        _login(client, user.email, "test-password")
        assert client.get("/my-schedule").status_code == 500
    rows = app.state.performance.dashboard()["groups"]
    assert any(row["node"] == "日程表" and row["metric"] == "request" and row["errors"] == 1 for row in rows)


@pytest.mark.parametrize("changes", [
    {"duration": -1}, {"duration": float("nan")}, {"duration": 120001},
    {"metric": "arbitrary"}, {"path": "/private-id"}, {"status": 1},
])
def test_client_samples_reject_unbounded_or_identifying_fields(changes):
    sample = {"node": "calendar", "metric": "request", "duration": 10, **changes}
    with pytest.raises(ValidationError):
        PerformanceBatch.model_validate({"samples": [sample]})


def test_parse_and_export_phases_keep_only_numeric_timings():
    from app.model.interview_experience import InterviewExperience
    from app.service.interview_experience_export import export_markdown
    from app.service.interview_experience_parser import parse_experience_text
    timings = RequestTimings()
    token = request_timings.set(timings)
    try:
        parse_experience_text("1 private question")
        export_markdown(InterviewExperience(owner_id="local", title="private title"), [])
    finally:
        request_timings.reset(token)
    assert set(timings.values) == {"parse_text", "markdown_render"}
    assert "private" not in repr(timings.values)
