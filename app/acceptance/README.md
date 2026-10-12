# Android 验收截图

每轮 Android 开发完成后，在 `app/acceptance/YYYY-MM-DD/` 保存真实设备或模拟器截图，并附 `manifest.json` 与当轮说明。日期使用北京时间。截图至少覆盖新增或修改页面的首屏、关键交互状态和必要的后续页面。

当前可用的自动采集脚本：`android/scripts/capture_acceptance.ps1`。先构建 Debug APK、启动已解锁的 Android 设备或模拟器，再运行脚本；默认设备序列号为 `emulator-5554`，也可传入 `-Serial`。脚本会安装 APK、打开调试用页面并通过 `adb screencap` 保存 PNG。

调试页面使用合成示例数据，仅验证原生界面的布局与分页；联网登录、服务端保存和系统文件选择需要另行在真实流程中验收。任何截图都不得包含真实账号、邀请内容、个人面经或其他敏感资料。
