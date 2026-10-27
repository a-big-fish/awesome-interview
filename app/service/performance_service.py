"""Bounded asynchronous performance storage, independent of the business database."""

import logging
import math
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread

from app.core.performance import METRIC_LABELS, NODE_LABELS

logger = logging.getLogger(__name__)


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * ratio) - 1)], 1) if ordered else 0


class PerformanceService:
    """Request threads only enqueue; a single worker handles disk I/O and retention."""

    def __init__(self, path: Path, enabled: bool = True, retention_days: int = 7):
        self.path = Path(path)
        self.enabled = enabled
        self.retention_days = retention_days
        self.queue: Queue = Queue(maxsize=2000)
        self.stopping = Event()
        self.worker: Thread | None = None
        self.ready = False
        self.dropped = 0
        self.write_failures = 0

    def start(self) -> None:
        if not self.enabled or self.worker and self.worker.is_alive():
            return
        self.stopping.clear()
        self.worker = Thread(target=self._write_loop, name="performance-writer", daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.stopping.set()
        if self.worker:
            self.worker.join(timeout=3)

    def record(self, node: str, source: str, metric: str, duration: float, status: int = 200) -> None:
        if not self.enabled:
            return
        try:
            self.queue.put_nowait((time.time(), node, source, metric, round(duration, 2), status))
        except Full:
            self.dropped += 1

    def _write_loop(self) -> None:
        connection = None
        last_prune = 0.0
        try:
            while not self.stopping.is_set() or not self.queue.empty():
                batch = []
                try:
                    batch.append(self.queue.get(timeout=.25))
                except Empty:
                    if not self.stopping.is_set() and (not self.ready or time.time() - last_prune >= 60):
                        pass
                    else:
                        continue
                for _ in range(63):
                    try:
                        batch.append(self.queue.get_nowait())
                    except Empty:
                        break
                try:
                    if connection is None:
                        self.path.parent.mkdir(parents=True, exist_ok=True)
                        connection = sqlite3.connect(self.path, timeout=.5)
                        connection.execute("PRAGMA journal_mode=WAL")
                        connection.execute("CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY, "
                                           "received REAL, node TEXT, source TEXT, metric TEXT, duration REAL, status INTEGER)")
                        connection.execute("CREATE INDEX IF NOT EXISTS sample_time ON samples(received)")
                    if batch:
                        connection.executemany("INSERT INTO samples(received,node,source,metric,duration,status) "
                                               "VALUES (?,?,?,?,?,?)", batch)
                        connection.execute("DELETE FROM samples WHERE id <= (SELECT MAX(id) FROM samples) - 100000")
                    now = time.time()
                    if now - last_prune >= 60:
                        connection.execute("DELETE FROM samples WHERE received < ?", (now - self.retention_days * 86400,))
                        last_prune = now
                    connection.commit()
                    self.ready = True
                except (OSError, sqlite3.Error) as exc:
                    self.ready = False
                    self.dropped += len(batch)
                    self.write_failures += 1
                    if self.write_failures == 1 or self.write_failures % 60 == 0:
                        logger.warning("Performance storage unavailable: %s", type(exc).__name__)
                    if connection:
                        connection.close()
                        connection = None
                    if self.stopping.wait(1):
                        # Shutdown must not wait indefinitely for a broken disk.
                        while not self.queue.empty():
                            try:
                                self.queue.get_nowait()
                                self.queue.task_done()
                                self.dropped += 1
                            except Empty:
                                break
                finally:
                    for _ in batch:
                        self.queue.task_done()
        finally:
            if connection:
                connection.close()

    def dashboard(self, hours: int = 24) -> dict:
        now = time.time()
        result = {"enabled": self.enabled, "ready": self.ready, "dropped": self.dropped,
                  "write_failures": self.write_failures, "queued": self.queue.qsize(),
                  "hours": hours, "groups": [], "trend": [], "slow": [],
                  "server_count": 0, "browser_count": 0, "errors": 0, "longtasks": 0}
        if not self.enabled:
            return result
        try:
            with sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True, timeout=.3) as connection:
                rows = connection.execute("SELECT received,node,source,metric,duration,status FROM samples "
                                          "WHERE received >= ? ORDER BY received LIMIT 100000", (now - hours * 3600,)).fetchall()
        except (OSError, sqlite3.Error):
            result["ready"] = False
            return result
        groups = defaultdict(list)
        buckets = [defaultdict(list) for _ in range(24)]
        slow = []
        for received, node, source, metric, duration, status in rows:
            groups[(node, source, metric)].append((duration, status))
            if metric == "request":
                result[f"{source}_count"] += 1
                if source == "server" and status >= 400:
                    result["errors"] += 1
                index = min(23, max(0, int((received - (now - hours * 3600)) / (hours * 150))))
                buckets[index][source].append(duration)
            if metric == "longtask":
                result["longtasks"] += 1
            threshold = 2500 if metric == "lcp" else 200 if metric == "longtask" else 1000
            if duration >= threshold or metric == "request" and (status == 0 or status >= 400):
                slow.append({"received": received, "node": NODE_LABELS.get(node, node),
                             "source": source, "metric": METRIC_LABELS.get(metric, metric), "metric_key": metric,
                             "duration": round(duration, 1), "status": status})
        for (node, source, metric), values in groups.items():
            durations = [item[0] for item in values]
            result["groups"].append({"node": NODE_LABELS.get(node, node), "source": source,
                                     "metric": metric, "metric_label": METRIC_LABELS.get(metric, metric),
                                     "count": len(values), "p50": percentile(durations, .5),
                                     "p95": percentile(durations, .95), "max": round(max(durations), 1),
                                     "errors": sum(status == 0 or status >= 400 for _, status in values)
                                     if metric == "request" else 0})
        result["groups"].sort(key=lambda row: row["p95"], reverse=True)
        result["trend"] = [{"received": now - hours * 3600 + index * hours * 150,
                            "server": percentile(bucket["server"], .95),
                            "browser": percentile(bucket["browser"], .95),
                            "count": len(bucket["server"]) + len(bucket["browser"])}
                           for index, bucket in enumerate(buckets)]
        result["slow"] = sorted(slow, key=lambda row: row["duration"], reverse=True)[:30]
        return result
