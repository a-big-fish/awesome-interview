# Android 原生页面视觉验收

设备：Android 15 模拟器，1080 × 2400，420 dpi。APK：`1.0.0-alpha3` Debug 构建。

- `01-native-event-top.png`：原生日程添加首屏，包括邀请解析入口、标题和类型。
- `02-native-event-reminders.png`：表单下半部，包括地点、备注、默认关闭的提醒与保存按钮。
- `03-native-export-page-1.png`：面经 PDF 第 1 页的原生预览。
- `04-native-export-page-2.png`：同一份面经 PDF 第 2 页，检查逐页切换。
- `05-native-export-settings.png`：展开导出设置，检查隐藏回答等选项。

导出样本由 `android/scripts/generate_acceptance_pdf.py` 生成，所有内容均为合成示例。此组截图验证页面布局；不代表已完成登录、服务端导出、保存文件或真机系统通知的端到端验收。
