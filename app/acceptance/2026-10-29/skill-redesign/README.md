# 技能审查后的原生界面重构验收

日期：2026-10-29。Android 15 模拟器，真实 APK 运行截图，使用本地合成日程和 PDF，无真实用户数据。

## 截图

| 文件 | 检查内容 |
| --- | --- |
| 01-native-event-top.png | 邀请快捷填写默认收起、输入框中文提示、顶栏更多图标 |
| 02-native-event-reminders.png | 提醒选项触控区域、保存与返回操作 |
| 03-native-export-page-1.png / 04-native-export-page-2.png | 单页 PDF 预览、分页与下载按钮 |
| 05-native-export-settings.png | 原生设置对话框完整显示隐藏选项及应用操作 |
| 06-native-home-buttons.png | 白底首页、日期选中层级、待办及日程列表 |
| 07-native-calendar-buttons.png / 09-next-day-overnight-event.png | 月历完整网格、标题及溢出提示、跨天事件 |
| 08-native-event-detail-buttons.png | 日程详情操作层级与文字删除入口 |
| 10-narrow-large-font.png | 360dp 宽、1.3 倍字体下的表单布局 |
| 11-narrow-keyboard.png | 同等窄屏大字体，真实点击输入框打开键盘；输入框可见，底部导航隐藏 |

默认截图为 1080 × 2400、420 dpi；窄屏截图临时使用 480 dpi 与 font_scale=1.3。脚本结束恢复模拟器原字体设置与 420 dpi。

## 发现并返工的问题

- 文本省略点按钮在窄框内换行：改为 vector drawable 图标后重拍。
- 月历压缩过度使“+N 项”贴边：回调为 60dp 行高后重拍。
- 键盘弹出仍有底部导航挤占表单：原生编辑界面响应 IME inset 隐藏底部导航，收起键盘时恢复。
- 导出设置仅有 150dp 高的小滚动区：改用系统 AlertDialog，保留应用操作可见。

## 验证与范围

- Android assembleDebug、lintDebug 通过。
- pytest：162 passed、1 skipped；有一项现有依赖弃用警告。
- 本轮重构原生首页、日历、日程及导出。登录、面经编辑等 WebView 内容未迁移，离线/线上写入及保存文件的完整端到端测试不属于本组静态截图证明范围。
- 本机安装与技能对比见 `android/SKILLS.md`；本项目设计约定见 `android/DESIGN.md`。
