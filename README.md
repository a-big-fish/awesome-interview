# Awesome Interview

面向求职者的日程与面经工作台，也保留企业集中安排面试的会议日程模块。仓库同时包含 Web 服务、Android 客户端和 Windows 桌面客户端。Web 服务使用 FastAPI 和 Jinja2；两个客户端连接同一个服务端账号与数据。

> 当前状态：Web 功能可运行；Android 为个人测试用 alpha 版，Windows 为个人测试版。客户端提醒、离线场景和安装流程仍需在更多真实设备上验收。iOS 尚未实现。

## 功能

- **个人日程**：录入面试、笔试、课程、会议等安排；解析会议邀请；查看日程冲突。
- **面试与面经**：逐题、全文或 Markdown／文字层 PDF 导入；记录多级追问、现场回答、复盘答案与面试感受；预览并导出 Markdown／PDF。
- **面经广场**：登录后浏览用户选择公开且有内容的面经，按面试时间排序、按公司筛选。
- **企业会议日程**：集中解析和安排会议、面试，并设置工作与休息时段。公开个人模式不会注册此模块。
- **客户端**：Android 提供原生待办首页、日历和系统提醒；Windows 提供托盘与系统提醒。两端保存受保护的本人只读快照，服务器不可用时可查看上次同步的内容。列表页在线切换时先显示会话内缓存，再在后台刷新。

## 仓库结构

| 目录 | 内容 |
| --- | --- |
| `app/` | Web 服务、页面、API、业务逻辑和静态资源 |
| `interviewschedule/` | 跨模块的时间处理工具 |
| `android/` | Android 应用，详见 [Android 说明](android/README.md) |
| `windows/` | Windows 桌面应用，详见 [Windows 说明](windows/README.md) |
| `tests/` | 自动化测试 |
| `scripts/` | 数据迁移及管理员维护脚本 |
| `mockups/` | 早期界面原型与合成示例简历 |

这是一个单仓库：`app/` 已是 Web 服务目录，`android/` 和 `windows/` 是客户端工程。三者共享服务端数据契约；目前没有独立的 `web/` 或通用 `app/` 客户端目录。

## 本地运行 Web

需要 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/)。在仓库根目录运行：

```bash
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8291
```

Windows PowerShell 可用 `Copy-Item .env.example .env` 代替 `cp`。访问 `http://127.0.0.1:8291/`。示例配置采用 `APP_MODE=local` 和 `STORAGE_BACKEND=memory`，无需数据库或 AI 密钥，重启后内存中的记录会消失。

本地模式包含个人与企业入口。要持久化，请配置 PostgreSQL 连接，并将 `STORAGE_BACKEND` 改为 `postgres`；`rustfs` 和 `minio` 也使用 PostgreSQL 保存元数据，另用对应 S3 兼容存储保存文件。上传的简历和运行数据都不应提交到 Git。

### 多用户个人模式

在 `.env` 中设置 `APP_MODE=public_personal`、持久化存储，以及你自己的 HTTPS `PUBLIC_BASE_URL`。此模式只开放个人应用与账号相关路由。注册默认关闭；如需邀请或开放注册，设置 `REGISTRATION_MODE`，并按需要配置邀请码、邮箱验证和 SMTP。对外部署前应检查 HTTPS、数据库备份、账号与文件访问控制；不要直接把开发服务器暴露到公网。

`.env.example` 只提供空凭据。AI 面试功能若使用外部模型，需要自行配置 `AI_PROVIDER`、`AI_API_BASE_URL`、`AI_API_KEY` 和模型名；普通日程与面经功能不依赖 AI 密钥。

## 构建客户端

客户端需要连接你部署的 HTTPS 服务。源码默认指向不可用的 `https://example.invalid`，不会自动连接本项目作者的服务器。

**Android**：安装 JDK 17、Android SDK Platform 36 和 Build Tools 36，然后在 `android/` 下运行：

```powershell
.\gradlew.bat assembleDebug -PserverOrigin=https://your-domain.example
```

**Windows**：安装 .NET 10 SDK，在根目录运行：

```powershell
dotnet publish windows/AwesomeInterview.Desktop/AwesomeInterview.Desktop.csproj -c Release -r win-x64 --self-contained true -o windows/publish/AwesomeInterview-win-x64
```

运行 Windows 客户端前，设置 `AWESOME_INTERVIEW_SERVER_URL` 为你的 HTTPS 服务地址；客户端使用 WebView2 Runtime。客户端的构建、提醒和离线限制详见各自目录的 README。

## 测试

```bash
uv run pytest -q
```

Android 可在 `android/` 执行 `./gradlew lintDebug`；Windows 可执行 `dotnet build windows/AwesomeInterview.Desktop/AwesomeInterview.Desktop.csproj`。自动化测试不能代替真实设备上的提醒、权限及离线验收。

## 安全与数据

- `.env`、本机数据库、`data/`、构建产物、签名材料和运行日志都应留在本机。提交前运行 `git status`，不要提交真实简历、面经或账号数据。
- `mockups/sample-resume.pdf` 及对应 HTML 是合成样例，仅供界面原型使用。
- 仓库历史可能仍保留早期开发环境的路径或域名；发布完整 Git 历史前应单独审查历史记录。
- 本地 `docs/` 以工作文档为主，默认被 Git 忽略；本 README 与客户端 README 包含公开运行所需信息。

## 许可证

本项目自有代码采用 [MIT License](LICENSE)。`app/static/vendor/` 中的第三方脚本保留各自文件头部的版权与许可证声明。
