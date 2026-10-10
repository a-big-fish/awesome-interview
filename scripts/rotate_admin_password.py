"""Generate a new admin password, revoke sessions, and save it outside Git."""

import os
import secrets
from datetime import datetime
from pathlib import Path

from app.core.config import Settings
from app.mapper.postgres_auth_mapper import PostgresAuthMapper
from app.service.auth_service import hash_password


def main() -> None:
    settings = Settings()
    if settings.storage_backend == "memory":
        raise SystemExit("管理员密码轮换需要 PostgreSQL 持久化后端")
    mapper = PostgresAuthMapper(settings)
    admin = mapper.find_user("admin")
    if not admin or not admin.is_admin:
        raise SystemExit("未找到 admin 管理员账号")

    password = secrets.token_urlsafe(36)
    path = Path("data") / f"admin-credentials-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(f"账号：admin\n密码：{password}\n")
    mapper.update_password(admin.id, hash_password(password))
    mapper.revoke_user_sessions(admin.id)
    print(f"管理员密码已更新，旧会话已失效。新凭据仅保存在：{path.resolve()}")


if __name__ == "__main__":
    main()
