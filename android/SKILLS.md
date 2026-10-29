# Android 技能选型与安装记录

检查日期：2026-10-29。技能安装在本机 `C:/Users/people/.codex/skills/`，不将第三方技能复制进应用源码。

| 来源 | 实际内容与适用范围 | 安装与本轮使用 |
| --- | --- | --- |
| [android/skills](https://github.com/android/skills) | Google 官方平台/工程技能，涵盖系统栏、性能、安全、测试、导航及 Compose 等；并非一套视觉主题 | 安装仓库全部 36 个技能。按技术栈选择；edge-to-edge 明确要求 Compose，当前 Java Views 不直接套用其中 Compose 代码 |
| [mobile-app-ui-design](https://github.com/ceorkm/mobile-app-ui-design) | 移动端布局、视觉层级、操作流程、拇指区域、排版与状态设计 | 安装并用于本轮原生重构。其网页样例、pt/px 尺寸和大段落间距按 Android dp/sp 与 48dp 触控标准适配 |
| [UI Skills 原始仓库](https://github.com/ibelick/ui-skills) | 博客介绍的技能集合；原仓库及社区目录应区分，不能把文章的数量当作当前仓库数量 | 选装 ui-skills-root、baseline-ui、improve-ui、fixing-accessibility。baseline-ui 和 fixing-accessibility 的 React/Tailwind/ARIA 代码不适用于 Java Views；improve-ui 只做审计与计划，不作为修改源码的执行技能 |

原始介绍链接：[SkillForge](https://skills.yangsir.net/skill/gh-mobile-app-ui-design)、[UI Skills 文章](https://www.alex908.com/zh/blog/ui-skills-181-design-skills)。安装使用 Codex skill-installer 的 GitHub 下载脚本，新安装技能下一轮会被自动发现。

本次读取的仓库提交：

- android/skills：`45fd1739a4dbca5452c3e936570797f7f6261cd7`
- ceorkm/mobile-app-ui-design：`0ad61f025fc647417d4b8fb0ca786cb493c5156a`
- ibelick/ui-skills：`59193a75432e5f41c6980f53b9e6a7bd56919947`

## 现有界面审视与修正

1. 顶栏两个大按钮常驻、整块色彩抢占层级：合并为有可访问名称的更多图标，首页改为白底，强调当天选择。
2. 表单起始的大空白邀请文本框挤占手动录入：改为可展开的快捷填写入口，增加中文提示、字段标签关联及输入边框。
3. 导出选项放在 150dp 小滚动区：改为原生设置对话框，保留可见的应用操作；预览页面不随设置展开而缩小。

图标第一次截图出现文本点换行，随后已换为 vector drawable；此类问题必须在截图中检查，不能只根据编译成功判断设计完成。
