"""Back up anonymous timing samples before optionally starting a fresh baseline.

Usage: uv run python scripts/archive_performance.py --clear
Archives remain under ignored data/, never in Git.
"""

import argparse
import json
import math
import sqlite3
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def archive_performance(database: Path, output: Path, clear: bool = False) -> dict:
    database = database.resolve()
    if not database.is_file():
        raise FileNotFoundError("Performance database does not exist")
    output.mkdir(parents=True, exist_ok=False)
    backup = output / "samples.sqlite3"
    # SQLite backup produces a consistent snapshot including committed WAL data.
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=3) as source:
        with sqlite3.connect(backup) as destination:
            source.backup(destination)
    with sqlite3.connect(backup) as snapshot:
        if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Performance backup failed its integrity check; samples were not cleared")
        rows = snapshot.execute(
            "SELECT id,received,node,source,metric,duration,status FROM samples ORDER BY id"
        ).fetchall()
    now = time.time()
    windows = {}
    for hours in (1, 24, 168, None):
        groups = defaultdict(list)
        for _, received, node, source, metric, duration, status in rows:
            if hours is None or received >= now - hours * 3600:
                groups[(node, source, metric)].append((duration, status))
        windows[str(hours) if hours else "all"] = []
        for (node, source, metric), samples in sorted(groups.items()):
            values = sorted(value for value, _ in samples)
            percentile = lambda ratio: round(values[math.ceil(len(values) * Decimal(str(ratio))) - 1], 2)
            windows[str(hours) if hours else "all"].append({
                "node": node, "source": source, "metric": metric, "count": len(values),
                "p50": percentile(.5), "p55": percentile(.55), "p95": percentile(.95),
                "max": max(values), "errors": sum(status == 0 or status >= 400 for _, status in samples),
            })
    maximum = max((row[0] for row in rows), default=0)
    summary = {"archived_at": datetime.now().astimezone().isoformat(),
               "sample_count": len(rows), "maximum_id": maximum, "unit": "ms",
               "percentile_method": "nearest_rank", "windows": windows}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    # Do not clear anything unless the complete snapshot and summaries are saved.
    deleted = 0
    if clear:
        with sqlite3.connect(database, timeout=3) as live:
            deleted = live.execute("DELETE FROM samples WHERE id <= ?", (maximum,)).rowcount
    receipt = {"archive": str(output.resolve()), "archived_samples": len(rows),
               "deleted_samples": deleted,
               "note": "Samples committed after the snapshot remain as new observations."}
    (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()
    database = args.database
    if database is None:
        from app.core.config import Settings
        database = Path(Settings().performance_db_path)
    output = args.output or Path("data/performance-baselines") / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    print(json.dumps(archive_performance(database, output, args.clear), ensure_ascii=True))
