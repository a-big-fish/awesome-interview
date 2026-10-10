"""Back up 1.0 data, then copy personal records into the 2.1 event table.

Usage: python scripts/migrate_prd21.py [--apply]
Without --apply, prints counts and checks resume links without writing.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.core.config import Settings
from app.mapper.postgres_my_resume_mapper import PostgresMyResumeMapper
from app.mapper.postgres_personal_event_mapper import PostgresPersonalEventMapper
from app.mapper.postgres_schedule_mapper import PostgresScheduleMapper
from app.mapper.storage_factory import build_resume_file_storage
from app.service.personal_migration_service import migrate_legacy_personal_entries
from app.service.personal_schedule_service import PersonalScheduleService

TABLES = ("interview_schedule_entries", "interview_resumes", "my_resume_profiles")


def backup_source(settings: Settings, destination: Path) -> dict[str, int]:
    """Write original rows and PDF objects before touching the new table."""
    destination.mkdir(parents=True, exist_ok=False)
    counts = {}
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as connection:
        for table in TABLES:
            rows = connection.execute(f"SELECT row_to_json(t) AS payload FROM {table} AS t").fetchall()
            with (destination / f"{table}.json").open("x", encoding="utf-8") as output:
                json.dump([row["payload"] for row in rows], output, ensure_ascii=False, default=str)
            counts[table] = len(rows)
    file_storage = build_resume_file_storage(settings)
    pdf_dir = destination / "resume-pdfs"
    pdf_dir.mkdir()
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as connection:
        resumes = connection.execute("SELECT id, pdf_path FROM interview_resumes").fetchall()
    missing_pdfs = []
    for resume in resumes:
        try:
            content = file_storage.read_pdf(resume["pdf_path"])
        except FileNotFoundError:
            missing_pdfs.append(resume["id"])
            continue
        (pdf_dir / f"{resume['id']}.pdf").write_bytes(content)
    counts["readable_resume_pdfs"] = len(list(pdf_dir.glob("*.pdf")))
    counts["missing_resume_pdfs"] = len(missing_pdfs)
    (destination / "missing_resume_ids.json").write_text(json.dumps(missing_pdfs), encoding="utf-8")
    (destination / "counts.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="back up and copy data")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    settings = Settings()
    if settings.storage_backend == "memory":
        raise SystemExit("内存存储无持久历史记录，迁移仅适用于 PostgreSQL 后端")
    legacy = PostgresScheduleMapper(settings=settings)
    profile = PostgresMyResumeMapper(settings=settings)
    legacy_personal = [entry for entry in legacy.list_all() if entry.source == "personal"]
    with psycopg.connect(settings.postgres_dsn) as connection:
        resume_ids = {row[0] for row in connection.execute("SELECT id FROM interview_resumes")}
    missing = [entry.id for entry in legacy_personal if entry.resume_id and entry.resume_id not in resume_ids]
    current_profile = profile.get()
    if current_profile and current_profile.resume_id not in resume_ids:
        missing.append("current-profile")
    print(f"历史记录 {len(legacy.list_all())}，个人记录 {len(legacy_personal)}，简历元数据 {len(resume_ids)}")
    if missing:
        raise SystemExit(f"发现 {len(missing)} 个失效简历关联，已停止")
    if not args.apply:
        print("预演完成；运行 --apply 执行本地备份及复制")
        return
    backup_dir = args.backup_dir or Path("data/migrations") / datetime.now().strftime("%Y%m%d-%H%M%S")
    counts = backup_source(settings, backup_dir)
    if counts["readable_resume_pdfs"] + counts["missing_resume_pdfs"] != counts["interview_resumes"]:
        raise SystemExit("简历文件清点数量不一致，已停止")
    if counts["missing_resume_pdfs"]:
        print(f"历史存储有 {counts['missing_resume_pdfs']} 个 PDF 已缺失，详情记录在备份目录")
    linked_ids = {entry.resume_id for entry in legacy_personal if entry.resume_id}
    if current_profile:
        linked_ids.add(current_profile.resume_id)
    missing_ids = set(json.loads((backup_dir / "missing_resume_ids.json").read_text(encoding="utf-8")))
    if linked_ids & missing_ids:
        raise SystemExit("个人面试或当前简历关联的 PDF 不可读取，已停止")
    personal_mapper = PostgresPersonalEventMapper(settings=settings)
    service = PersonalScheduleService(personal_mapper, profile)
    report = migrate_legacy_personal_entries(legacy, service, dry_run=False)
    for old in legacy_personal:
        new = service.get_event(old.id)
        if not new or new.legacy_entry_id != old.id or new.start_at != old.start_time or new.end_at != old.end_time or new.resume_id != old.resume_id:
            raise SystemExit(f"迁移对账失败：{old.id}")
    print(f"备份位置 {backup_dir.resolve()}")
    print(f"个人记录：新增 {report.created_count}，已存在 {report.existing_count}，核对 {report.legacy_count}")


if __name__ == "__main__":
    main()
