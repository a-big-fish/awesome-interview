# Awesome Interview Android

Android 测试版（`1.0.0-alpha3`）。首页、月／周日历、日程添加与编辑、面经逐页导出为原生界面；登录、面经列表与其他在线业务暂时复用个人站点。原生层还提供系统日程提醒、加密的本人只读缓存和文件选择。

## 本地构建

需要 JDK 17、Android SDK Platform 36、Build Tools 36 和可访问 Google Maven 的网络。

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17.0.13'
$env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
.\gradlew.bat assembleDebug -PserverOrigin=https://your-domain.example
```

将 `your-domain.example` 换成自己的 HTTPS 服务域名；不指定 `serverOrigin` 时会使用不可用的 `https://example.invalid`，不会连接作者的服务。调试 APK 位于 `app/build/outputs/apk/debug/`。当前不包含发布签名配置。首次登录和在线编辑需要服务器运行；服务器关闭后仅可通过设备锁屏验证查看上次成功同步的本人内容。系统提醒仍需真机验收。

底部导航包括首页、日历、添加、面经、我的；点击顶部应用名称可进入面经广场、我的面试或网页日程表。日历内左右滑切换月/周视图，日期下方显示当天安排。待办会同步到当前账号，断网时只读。原生日程表单支持粘贴邀请解析、逐项核对、重叠确认和提醒设置。面经列表中打开“预览与导出”后，原生页面按照服务端 PDF 的实际分页逐页展示，可保存当前页 PNG 或整份 PDF。PDF 导出需要联网，生成的临时文件放在应用私有缓存。

每轮 Android 开发的页面截图保存在仓库根目录的 `app/acceptance/YYYY-MM-DD/`；采集方式与截图范围见 [验收说明](../app/acceptance/README.md)。
