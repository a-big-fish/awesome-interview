# Awesome Interview Android

Android 1.0-A.1 测试版（`1.0.0-alpha2`）。首页和月／周日历为原生界面，其他在线业务复用个人站点；原生层还提供系统日程提醒、加密的本人只读缓存和文件选择。

## 本地构建

需要 JDK 17、Android SDK Platform 36、Build Tools 36 和可访问 Google Maven 的网络。

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17.0.13'
$env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
.\gradlew.bat assembleDebug -PserverOrigin=https://your-domain.example
```

将 `your-domain.example` 换成自己的 HTTPS 服务域名；不指定 `serverOrigin` 时会使用不可用的 `https://example.invalid`，不会连接作者的服务。调试 APK 位于 `app/build/outputs/apk/debug/`。当前不包含发布签名配置。首次登录和在线编辑需要服务器运行；服务器关闭后仅可通过设备锁屏验证查看上次成功同步的本人内容。系统提醒仍需真机验收。

底部导航包括首页、日历、添加、面经、我的；点击顶部应用名称可进入面经广场、我的面试或网页日程表。日历内左右滑切换月/周视图，日期下方显示当天安排。待办会同步到当前账号，断网时只读。
