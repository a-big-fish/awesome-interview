# Awesome Interview for Windows · App 1.0-W

Windows 10/11 x64 测试版。运行 `AwesomeInterview.exe` 前，先设置自己的 HTTPS 服务地址。首次在线登录后，应用会同步个人日程与面经；服务器暂时不可用时可查看最近一次同步的只读副本。

## 使用

- 在 PowerShell 中设置 `$env:AWESOME_INTERVIEW_SERVER_URL = 'https://your-domain.example'`，再从同一个终端启动程序。不设置或地址不合法时，客户端使用不可用的 `https://example.invalid`，不会连接作者的服务。需要安装 WebView2 Runtime。
- 在网页版为单条日程勾选提醒。Windows 客户端同步后尝试登记系统计划通知；若系统不支持，则窗口关闭后保持托盘运行以发送运行时提醒。点击托盘图标可重新打开窗口，通过托盘菜单“退出程序”可完全退出。
- 点击“立即同步”可马上刷新本地快照；应用运行中也会定期同步。离线内容可能落后于其他设备，请看左下角最近同步时间。
- “退出登录”会清除本机快照、会话及待触发提醒。解压目录可直接删除；个人缓存位于当前 Windows 用户的 `%LOCALAPPDATA%\AwesomeInterview`。

## 构建

安装 .NET 10 SDK 后，在仓库根目录运行：

```powershell
dotnet publish windows/AwesomeInterview.Desktop/AwesomeInterview.Desktop.csproj -c Release -r win-x64 --self-contained true -o windows/publish/AwesomeInterview-1.0-W-win-x64
```

工程版本号 `1.0-W` 独立于 Web 与 Android 版本。

## 当前验收范围

已完成 x64 构建和本机启动烟测。真实账号登录、文件导入/导出、十条提醒送达、系统关机跨时区、完全退出后的计划通知与跨账号清理仍需手动走查；在这些测试完成前不视作正式发行版。
