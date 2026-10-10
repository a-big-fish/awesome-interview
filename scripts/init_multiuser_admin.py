"""Back up and assign existing local personal data to the admin account.

Run without --apply for a read-only inventory. With --apply, back up affected
rows and resume files first, then atomically change their ownership.
"""

import argparse
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.core.config import Settings
from app.mapper.postgres_auth_mapper import PostgresAuthMapper
from app.mapper.postgres_resume_mapper import PostgresResumeMapper
from app.mapper.storage_factory import build_resume_file_storage
from app.model.auth import AuthUser
from app.service.auth_service import hash_password


def inventory(connection) -> tuple[list[dict], dict | None, list[dict], set[str]]:
    events = connection.execute(
        "SELECT * FROM personal_schedule_events WHERE owner_id = 'local' ORDER BY id"
    ).fetchall()
    profile = connection.execute(
        "SELECT * FROM my_resume_profiles WHERE id = 'default'"
    ).fetchone()
    resume_ids = {row["payload"].get("resume_id") for row in events}
    if profile:
        resume_ids.add(profile["resume_id"])
    resume_ids.discard(None)
    resumes = connection.execute(
        "SELECT * FROM interview_resumes WHERE id = ANY(%s) ORDER BY id",
        (list(resume_ids),),
    ).fetchall() if resume_ids else []
    return events, profile, resumes, resume_ids


def check_files(settings: Settings, resumes: list[dict], destination: Path | None = None) -> None:
    storage = build_resume_file_storage(settings)
    if destination:
        destination.mkdir(parents=True)
    for row in resumes:
        resume_id = row["id"]
        pdf = storage.read_pdf(row["pdf_path"])
        if destination:
            (destination / f"{resume_id}.pdf").write_bytes(pdf)
        if row["text_path"]:
            text = storage.read_text(row["text_path"])
            if destination:
                (destination / f"{resume_id}.txt").write_text(text, encoding="utf-8")
        for image in row["images"] or []:
            content = storage.read_image(image["file_path"])
            if destination:
                (destination / f"{resume_id}-{image['image_id']}.png").write_bytes(content)


def dump_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if settings.storage_backend == "memory":
        raise SystemExit("多用户迁移需要 PostgreSQL 持久化后端")

    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as connection:
        events, profile, resumes, resume_ids = inventory(connection)
        if len(resumes) != len(resume_ids):
            raise SystemExit("现有个人日程引用了缺失的简历元数据，已停止")
        print(f"待迁移：个人日程 {len(events)} 项，当前简历配置 {int(profile is not None)} 项，关联简历 {len(resumes)} 份")
        check_files(settings, resumes)
        has_users_table = connection.execute(
            "SELECT to_regclass('personal_users') AS table_name"
        ).fetchone()["table_name"] is not None
        existing = connection.execute(
            "SELECT id FROM personal_users WHERE username = 'admin'"
        ).fetchone() if has_users_table else None
        if existing:
            print("admin 账号已存在；不会重置密码")
        if not args.apply:
            print("只读预演通过；使用 --apply 先备份，再执行归属迁移")
            return

        backup_dir = Path("data/migrations") / f"multiuser-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        dump_json(backup_dir / "personal_schedule_events.json", events)
        dump_json(backup_dir / "my_resume_profile.json", profile)
        dump_json(backup_dir / "linked_resumes.json", resumes)
        check_files(settings, resumes, backup_dir / "resume-files")

    PostgresAuthMapper(settings=settings)
    PostgresResumeMapper(settings=settings)
    credentials_path = Path("data/admin-initial-credentials.txt")
    new_password: str | None = None
    if not existing:
        if credentials_path.exists():
            raise SystemExit(f"初始密码文件已存在，请先核对：{credentials_path}")
        new_password = secrets.token_urlsafe(15)
        descriptor = os.open(credentials_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(f"账号：admin\n密码：{new_password}\n")

    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as connection:
        if existing:
            admin_id = existing["id"]
        else:
            admin = AuthUser(username="admin", password_hash=hash_password(new_password),
                             email_verified=True, is_admin=True)
            inserted = connection.execute("""
                INSERT INTO personal_users
                    (id, email, username, password_hash, email_verified, is_admin, created_at)
                VALUES (%s, NULL, %s, %s, TRUE, TRUE, %s)
                ON CONFLICT DO NOTHING RETURNING id
            """, (admin.id, admin.username, admin.password_hash, admin.created_at)).fetchone()
            if not inserted:
                raise RuntimeError("创建 admin 账号失败，未迁移数据")
            admin_id = inserted["id"]

        for row in events:
            payload = dict(row["payload"])
            payload["owner_id"] = admin_id
            connection.execute("""
                UPDATE personal_schedule_events SET owner_id = %s, payload = %s
                WHERE id = %s AND owner_id = 'local'
            """, (admin_id, Json(payload), row["id"]))
        if profile:
            connection.execute("""
                INSERT INTO my_resume_profiles (id, resume_id, updated_at)
                VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING
            """, (admin_id, profile["resume_id"], profile["updated_at"]))
        if resume_ids:
            existing_owners = connection.execute(
                "SELECT DISTINCT owner_id FROM interview_resumes WHERE id = ANY(%s)",
                (list(resume_ids),),
            ).fetchall()
            if any(row["owner_id"] not in {"local", admin_id} for row in existing_owners):
                raise RuntimeError("关联简历已有其他所有者，已取消迁移")
            connection.execute("""
                UPDATE interview_resumes SET owner_id = %s
                WHERE id = ANY(%s) AND owner_id = 'local'
            """, (admin_id, list(resume_ids)))
        connection.commit()

    dump_json(backup_dir / "report.json", {
        "admin_user_id": admin_id, "events": len(events),
        "linked_resumes": len(resumes), "profile": bool(profile),
    })
    print(f"迁移完成。备份：{backup_dir.resolve()}")
    if new_password:
        print(f"初始账号密码仅保存在：{credentials_path.resolve()}")


if __name__ == "__main__":
    main()
