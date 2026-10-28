"""Anonymous performance nodes and request-scoped database timings."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from threading import Lock
from time import perf_counter
from typing import Any

import psycopg

NODE_LABELS = {
    "calendar": "日程表", "event": "日程详情", "event_write": "日程保存/完成",
    "event_parse": "邀请解析", "plaza": "面经广场", "experiences": "我的面经",
    "editor": "面经编辑页", "draft": "面经草稿保存", "experience_write": "面经修改",
    "parse": "面经文本/文件解析", "pdf": "PDF 导出", "markdown": "Markdown 导出",
    "export": "导出预览", "interviews": "面试工作台", "profile": "个人设置",
    "login": "登录", "register": "注册", "mobile": "客户端同步/API",
    "resume_state": "当前简历状态", "resume_file": "简历文件",
}
METRIC_LABELS = {
    "request": "请求", "auth": "会话鉴权", "db_connect": "数据库连接",
    "db_pool_wait": "数据库连接池借用等待",
    "db_query": "数据库执行/提交", "ttfb": "首字节 TTFB", "load": "页面加载",
    "lcp": "最大内容绘制 LCP", "longtask": "主线程长任务", "cache_render": "缓存页面呈现",
    "parse_text": "文本规则解析", "parse_markdown": "Markdown 结构解析",
    "resume_storage": "简历文件存储读取",
    "pdf_extract": "PDF 文本提取", "pdf_render": "PDF 排版生成", "markdown_render": "Markdown 导出生成",
}
CLIENT_METRICS = {"request", "ttfb", "load", "lcp", "longtask", "cache_render"}


def node_for_path(path: str, method: str = "GET") -> str | None:
    """Map paths to fixed names; never retain IDs, query strings, or titles."""
    path = path.split("?", 1)[0].rstrip("/")
    if path == "/auth/login":
        return "login"
    if path == "/auth/register":
        return "register"
    if path.startswith("/api/mobile/v1/"):
        return "mobile"
    if path.startswith("/resumes/") and path.endswith(("/pdf", "/download")):
        return "resume_file"
    if not path.startswith("/my-schedule"):
        return None
    tail = path[len("/my-schedule"):]
    if tail == "/resume/current":
        return "resume_state"
    if tail.startswith(("/admin", "/telemetry")):
        return None
    if tail in {"", "/new"}:
        return "calendar"
    if tail == "/parse":
        return "event_parse"
    if tail.startswith("/events"):
        return "event" if method == "GET" else "event_write"
    if tail.startswith("/interviews") or tail == "/resume":
        return "interviews"
    if tail.startswith("/profile"):
        return "profile"
    if tail.startswith("/experiences/plaza"):
        return "plaza"
    if tail == "/experiences":
        return "experiences"
    if tail.startswith("/experiences/"):
        suffix = tail.rsplit("/", 1)[-1]
        return {"export.pdf": "pdf", "export.md": "markdown", "export": "export",
                "draft": "draft", "parse": "parse", "parse-file": "parse"}.get(
                    suffix, "editor" if method == "GET" else "experience_write")
    return None


@dataclass
class RequestTimings:
    values: dict[str, float] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def add(self, name: str, duration: float) -> None:
        with self.lock:
            self.values[name] = self.values.get(name, 0) + duration


request_timings: ContextVar[RequestTimings | None] = ContextVar("performance_timings", default=None)


@contextmanager
def measure_phase(name: str):
    timings = request_timings.get()
    if timings is None:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        timings.add(name, (perf_counter() - started) * 1000)


def timed_phase(name: str):
    """Time an existing synchronous operation without retaining its arguments."""
    def decorate(function):
        @wraps(function)
        def measured(*args, **kwargs):
            with measure_phase(name):
                return function(*args, **kwargs)
        return measured
    return decorate


class _TimedDatabase:
    """Delegate psycopg's interface while measuring blocking I/O, without SQL logging."""

    def __init__(self, target: Any):
        self._target = target

    def __getattr__(self, name):
        return getattr(self._target, name)

    def __enter__(self):
        self._target.__enter__()
        return self

    def __exit__(self, *args):
        with measure_phase("db_query"):
            return self._target.__exit__(*args)

    def execute(self, *args, **kwargs):
        with measure_phase("db_query"):
            result = self._target.execute(*args, **kwargs)
        return self if result is self._target else result

    def executemany(self, *args, **kwargs):
        with measure_phase("db_query"):
            return self._target.executemany(*args, **kwargs)

    def cursor(self, *args, **kwargs):
        return _TimedDatabase(self._target.cursor(*args, **kwargs))

    def commit(self):
        with measure_phase("db_query"):
            return self._target.commit()

    def rollback(self):
        with measure_phase("db_query"):
            return self._target.rollback()


def timed_postgres_connect(*args, **kwargs):
    from app.core.postgres_pool import connection
    return connection(*args, **kwargs)
