import json
import sqlite3
import time

import pytest

from scripts.archive_performance import archive_performance


def test_archive_preserves_raw_samples_and_p50_p55_p95_before_clear(tmp_path):
    database = tmp_path / "performance.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE samples(id INTEGER PRIMARY KEY,received REAL,node TEXT,source TEXT,metric TEXT,duration REAL,status INTEGER)")
        connection.executemany("INSERT INTO samples(received,node,source,metric,duration,status) VALUES(?,?,?,?,?,?)",
                               [(time.time(), "plaza", "server", "request", value, 200) for value in range(1, 101)])
    output = tmp_path / "archive"
    result = archive_performance(database, output, clear=True)
    assert result["deleted_samples"] == result["archived_samples"] == 100
    with sqlite3.connect(output / "samples.sqlite3") as backup:
        assert backup.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 100
    with sqlite3.connect(database) as live:
        assert live.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0
    summary = json.loads((output / "summary.json").read_text())
    group = summary["windows"]["1"][0]
    assert (group["p50"], group["p55"], group["p95"]) == (50, 55, 95)
    with pytest.raises(FileExistsError):
        archive_performance(database, output, clear=True)


def test_missing_database_is_never_created_by_archive(tmp_path):
    with pytest.raises(FileNotFoundError):
        archive_performance(tmp_path / "missing.sqlite3", tmp_path / "backup", clear=True)
