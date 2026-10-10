"""Locally reset an account password when email recovery is unavailable."""

import argparse
import os
import secrets
from datetime import datetime
from pathlib import Path

from app.core.config import Settings
from app.mapper.postgres_auth_mapper import PostgresAuthMapper
from app.service.auth_service import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identifier", help="需重置密码的邮箱或管理员用户名")
    args = parser.parse_args()
    settings = Settings()
    if settings.storage_backend == "memory":
        raise SystemExit("密码重置需要 PostgreSQL 持久化后端")
    identifier = args.identifier.strip().casefold()
    if not identifier or len(identifier) > 254:
        raise SystemExit("请输入有效的邮箱或用户名")
    mapper = PostgresAuthMapper(settings)
    user = mapper.find_user(identifier)
    if not user:
        raise SystemExit("未找到该账号")

    password = secrets.token_urlsafe(15)
    path = Path("data/password-resets") / f"{user.id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(f"账号：{identifier}\n临时密码：{password}\n")
    mapper.update_password(user.id, hash_password(password))
    mapper.revoke_user_sessions(user.id)
    print(f"密码已重置，旧会话已失效。临时凭据仅保存在：{path.resolve()}")


if __name__ == "__main__":
    main()
