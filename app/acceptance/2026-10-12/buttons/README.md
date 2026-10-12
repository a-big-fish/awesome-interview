# Android 按钮样式验收

设备：Android 15 模拟器，1080 × 2400，420 dpi。构建：`1.0.0-alpha3` Debug。

本轮统一了原生日程、面经导出、首页、日历与顶栏的操作按钮。绿色实底用于主要操作，浅绿色用于辅助操作，描边用于返回和翻页，浅红色用于删除；禁用翻页按钮使用灰态。可点击按钮最小触控高度为 48dp。点击时有涟漪反馈，底部当前页面保持选中底色。

截图：

- `01-native-event-top.png`、`02-native-event-reminders.png`：日程表单上、下半部。
- `03-native-export-page-1.png`、`04-native-export-page-2.png`：导出预览及翻页操作。
- `05-native-export-settings.png`：导出设置展开状态。
- `06-native-home-buttons.png`：首页新建按钮与底部导航。
- `07-native-calendar-buttons.png`：日历翻页与月/周视图切换。
- `08-native-event-detail-buttons.png`：日程编辑、删除、返回的视觉层级。

全部为模拟器直接截取的运行截图。日程详情、首页和 PDF 使用本地合成示例，不含真实用户资料；此组截图验证视觉和布局，不代表服务端保存或导出的端到端验收。
