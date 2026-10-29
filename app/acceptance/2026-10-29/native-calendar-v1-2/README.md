# 原生日历及完成操作验收

Android 15 模拟器，1080 × 2400，420 dpi；Debug APK 实际运行截图。全部日程及 PDF 是本地合成数据。

- `07-native-calendar-buttons.png`：月历显示首条事件标题、完成标记及溢出数量；长标题省略，点击日期查看完整当天列表。
- `08-native-event-detail-buttons.png`：原生详情新增“标记为已完成”操作；成功后详情显示完成标记和“恢复为未完成”。
- `09-next-day-overnight-event.png`：跨天日程在次日显示延续标记。
- 其余截图为添加日程及导出预览的布局回归检查。

验证结果：Android 构建与 lint 通过；pytest 为 162 passed、1 skipped。移动端完成接口测试覆盖 CSRF、账号隔离、完成/恢复、严格布尔校验及日程时间不变。截图不包含线上账号操作，尚未执行服务端部署后的手机端到端验收。
