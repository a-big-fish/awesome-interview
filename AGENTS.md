# AGENTS.md

## 项目概述

本仓库是「日程工作台」，在同一个 FastAPI 部署中提供企业「会议日程」和个人「我的日程」两个应用。两者共享会议邀请解析核心，拥有独立路由、业务模型和日程存储。企业应用支持密集面试时间表及每周工作/休息时段配置；个人应用支持多类型事件、面试工作台和当前 PDF 简历。旧会议详情保留简历与 AI 面试辅助。

当前范围：

- FastAPI + Jinja2 提供 SSR 页面和 JSON API。
- PyMuPDF 负责 PDF 文本、元数据和图片提取。
- Pydantic v2 负责模型和请求校验。
- 存储后端由 `.env` 的 `STORAGE_BACKEND` 选择 Memory、PostgreSQL、RustFS 或 MinIO；Memory 后端重启后元数据丢失。AI 模型 Provider 也通过 `.env` 配置。
- 上传简历包含个人信息，严禁提交到 Git 或复制进测试。

## 常用命令

使用 uv 管理 Python 环境和依赖：

```bash
# 同步依赖
uv sync

# 启动本地开发服务
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8291

# 运行完整测试
uv run pytest -q
```

Python 版本要求见 `pyproject.toml`；当前项目至少支持 Python 3.10。修改依赖时必须同时更新 `pyproject.toml` 和 `uv.lock`。

## 目录结构

```text
app/
├─ main.py                         # FastAPI 应用入口和页面路由注册
├─ controller/                     # HTTP 页面和 API 控制器
│  └─ schema/                      # DTO（请求）与 VO（响应）
├─ service/                        # 业务规则、会议/简历解析、照片筛选、AI 辅助入口
├─ mapper/                         # 元数据 Mapper 与简历文件存储抽象/实现
├─ model/                          # 领域模型和枚举
├─ core/                           # 依赖注入、异常、配置
├─ templates/                      # Jinja2 页面
└─ static/                         # CSS / JS
interviewschedule/
└─ utils/                          # 跨层通用工具（时间转换等）
tests/                             # 自动化测试
test/                              # PyMuPDF 探索脚本和素材，不要作为生产代码入口
docs/                              # 本地 PRD、规划、启动与架构文档；Git 忽略
data/                              # 运行期简历、图片和本地数据；已忽略，不提交
mockups/                           # 原型 HTML/CSS/JS 与截图
```

## 分层规则

- Controller 只处理 HTTP 输入输出、校验和响应结构，不写业务规则。
- Service 承担业务编排和领域规则，不直接依赖 FastAPI 的 `Request` 对象。
- Mapper 与 `ResumeFileStorage` 封装存储边界；新增存储实现时不要让 Service 直接操作数据库或对象存储细节。
- `controller/schema/*_dto.py` 用于外部请求进入应用；`*_vo.py` 用于页面或客户端响应。
- 领域模型位于 `app/model/`，必要时使用 Pydantic 校验时间区间和状态。
- 时间处理必须保留时区信息，默认使用 `Asia/Shanghai`。
- 通用时间工具放在 `interviewschedule/utils/`；`app/core/time_utils.py` 仅作为兼容导出。

## 编码风格

- 使用 4 空格缩进，遵循 PEP 8。
- 模块、函数、变量使用 `snake_case`；类使用 `PascalCase`；常量使用 `UPPER_SNAKE_CASE`。
- 文件名使用英文；测试文件命名为 `test_<module>.py`。
- 公共接口添加类型注解和简短 docstring。
- 新页面路由放在 `page_controller.py`；JSON API 按 `schedule_controller.py` 或 `resume_controller.py`、`ai_interview_controller.py` 的既有分组放置。
- 前端资源放在 `app/static/`；不要把生产交互逻辑放在 `mockups/` 中。

## 测试要求

- 修改代码后运行 `uv run pytest -q`。
- 会议邀请解析必须覆盖腾讯会议等平台、时间格式、时区、缺失会议号或链接的错误分支。
- 简历解析测试使用临时目录或 fixture 生成的小型 PDF，不要提交真实候选人简历。
- API 测试使用 FastAPI `TestClient`，需要时用依赖注入替换 Service、Mapper 或文件存储，避免污染全局状态。
- 涉及时间表 UI、上传简历、详情页、PDF 预览或 AI 对话时，先运行服务手动验证主流程。
- AI Provider 测试使用 mock transport 或静态 Provider，不能在测试中请求真实远程模型。
- 不要提交 `.env`；新增配置时同步更新 `.env.example`。
- `docs/` 是本地文档目录，已加入 `.gitignore`；更新文档时保留在本地，不用 `git add -f` 强制提交。

## 版本管理

- 每个独立功能或修复单独提交，提交信息使用简洁祈使句，例如：
  - `feat: add meeting parser`
  - `fix: normalize naive meeting time`
  - `test: cover resume parser errors`
- 提交前检查 `git status` 和 `git diff --stat`，不要提交 `.venv/`、`__pycache__/`、`data/`、真实简历或可识别个人身份的数据。
- 依赖变更需包含 `pyproject.toml` 和 `uv.lock`，并在提交说明中说明原因。
- PR 应说明目的、测试方式、关联需求或 issue；UI 变更附截图，解析规则变更附输入/输出示例。
