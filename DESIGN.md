---
name: Kinbo
description: Zotero 内的证据伴读界面：保留论文主工作面，让对话始终可返回原文。
colors:
  light-bg: '#f7f8f9'
  light-surface: '#ffffff'
  light-hover: '#e9ecef'
  light-ink: '#23282d'
  light-muted: '#626a73'
  light-line: '#d5d9de'
  light-control: '#8c959f'
  light-accent: '#245d70'
  light-selected: '#edf3f5'
  light-focus: '#246579'
  light-primary: '#263139'
  light-on-primary: '#ffffff'
  light-danger: '#a12f39'
  light-error-bg: '#fff1f1'
  dark-bg: '#202327'
  dark-surface: '#262a2f'
  dark-hover: '#343b42'
  dark-ink: '#e5e9ed'
  dark-muted: '#b0b8c1'
  dark-line: '#424a52'
  dark-control: '#697680'
  dark-accent: '#96c8dc'
  dark-selected: '#293e49'
  dark-focus: '#a1d2e4'
  dark-primary: '#dce5eb'
  dark-on-primary: '#20282e'
  dark-danger: '#ffb0b6'
  dark-error-bg: '#3b282e'
  evidence-highlight: rgba(255,199,42,.45)
typography:
  title:
    fontFamily: Bahnschrift, Avenir Next, sans-serif
    fontSize: 17px
    fontWeight: 600
    lineHeight: 1.2
  body:
    fontFamily: Aptos, Segoe UI Variable Text, PingFang SC, Microsoft YaHei UI, sans-serif
    fontSize: 13px
    lineHeight: 1.65
  label:
    fontFamily: Aptos, Segoe UI Variable Text, PingFang SC, Microsoft YaHei UI, sans-serif
    fontSize: 12px
    lineHeight: 1.65
  message-heading:
    fontFamily: Aptos, Segoe UI Variable Text, PingFang SC, Microsoft YaHei UI, sans-serif
    fontSize: 14px
    lineHeight: 1.5
  empty-title:
    fontFamily: Aptos, Segoe UI Variable Text, PingFang SC, Microsoft YaHei UI, sans-serif
    fontSize: 15px
    lineHeight: 1.65
  code:
    fontFamily: Cascadia Code, Consolas, monospace
    fontSize: 12px
    lineHeight: 1.65
rounded:
  control: 6px
  input: 8px
spacing:
  compact: 4px
  control: 8px
  region: 12px
  message: 16px
  empty: 24px
components:
  button-send:
    backgroundColor: '{colors.light-primary}'
    textColor: '{colors.light-on-primary}'
    typography: '{typography.body}'
    rounded: '{rounded.control}'
    padding: 4px 12px
  button-send-hover:
    backgroundColor: '{colors.light-ink}'
    textColor: '{colors.light-surface}'
  button-send-dark:
    backgroundColor: '{colors.dark-primary}'
    textColor: '{colors.dark-on-primary}'
  button-send-dark-hover:
    backgroundColor: '{colors.dark-ink}'
    textColor: '{colors.dark-surface}'
  button-neutral:
    backgroundColor: transparent
    textColor: '{colors.light-ink}'
    typography: '{typography.body}'
    rounded: '{rounded.control}'
    padding: 4px 8px
  button-neutral-hover:
    backgroundColor: '{colors.light-hover}'
  button-neutral-dark:
    backgroundColor: transparent
    textColor: '{colors.dark-ink}'
  button-neutral-dark-hover:
    backgroundColor: '{colors.dark-hover}'
  button-icon:
    typography: '{typography.body}'
    rounded: '{rounded.control}'
    padding: '0'
    width: 32px
  button-starter:
    typography: '{typography.body}'
    rounded: '{rounded.control}'
    padding: 4px 8px
    width: 100%
  input-question:
    backgroundColor: '{colors.light-surface}'
    textColor: '{colors.light-ink}'
    typography: '{typography.body}'
    rounded: '{rounded.input}'
    padding: 4px 8px
    width: 100%
  input-question-dark:
    backgroundColor: '{colors.dark-surface}'
    textColor: '{colors.dark-ink}'
  link-evidence:
    textColor: '{colors.light-accent}'
    typography: '{typography.label}'
  link-evidence-dark:
    textColor: '{colors.dark-accent}'
  selection:
    backgroundColor: '{colors.light-selected}'
    textColor: '{colors.light-ink}'
    typography: '{typography.label}'
    rounded: '{rounded.control}'
    padding: 8px
  selection-dark:
    backgroundColor: '{colors.dark-selected}'
    textColor: '{colors.dark-ink}'
  disclosure-settings:
    textColor: '{colors.light-muted}'
    typography: '{typography.body}'
    padding: 4px 0
  message:
    backgroundColor: '{colors.light-surface}'
    textColor: '{colors.light-ink}'
    typography: '{typography.body}'
    padding: 16px 0
  message-error:
    backgroundColor: '{colors.light-error-bg}'
    textColor: '{colors.light-danger}'
    typography: '{typography.body}'
    rounded: '{rounded.control}'
    padding: 8px
  message-error-dark:
    backgroundColor: '{colors.dark-error-bg}'
    textColor: '{colors.dark-danger}'
---

# Design System: Kinbo

## Overview

**Creative North Star: "证据伴读"**

Kinbo 是沿论文页边展开的阅读工具。视觉语言专业、精致、克制，以石墨色界面、连续阅读面、清楚的分界和可返回原文的物理页码建立秩序。PDF 保持主工作面，品牌标记提供身份，颜色服务证据与状态。

本文件从本轮论文对话侧栏与菜单收敛的最终源码提取，适用于 Zotero 桌面 XHTML/Gecko 环境。后台 Web 控制页保留原设计；上游首选项、API 编辑器、翻译菜单及插件管理器身份仍有独立迁移任务。不得据此宣称全产品已完成 UI 迁移。

方向沿用用户确认的「证据伴读」。Taste app-screen 记录为 Achromatic ledger（seed 264691230），Hallmark 按 Custom app 审查，Impeccable 按 Operate code-first 实施。未运行 concept-seed；方向依据与第一屏策略保存在 docs/ui/paper-chat-brief.md。

**Key Characteristics:**

- 连续阅读面与细线分区，避免聊天气泡墙。
- 本地字体、紧凑控件和明确的键盘焦点。
- 浅深色语义一致，证据、失败与忙碌都有文字说明。
- 响应侧栏自身宽度，保持 PDF 与发送操作可达。

## Colors

中性色承担阅读与操作秩序，低饱和的青蓝色标出证据；浅深色按同一语义成对使用。frontmatter 是数值规范，不在正文另立一套颜色值。正文与辅助文字的对比度目标（4.5:1），控件边缘与焦点目标（3:1）；应按实际组合与状态核验。

原始值位于 `plugin/paper_chat.css` 的 `:root`，使用独立的 `--kinbo-light-*` / `--kinbo-dark-*` 前缀；运行时语义 token 的映射限于 `.kinbo-paper-chat`，不修改宿主通用样式。字体、圆角、间距与时长当前复用 `light` 前缀下的共享原始值，深色模式只重映射颜色。

### Primary

- **证据青蓝**：`light-accent` / `dark-accent` 用于页码、外链、输入光标和联网复选框。
- **发送石墨 / 雾白**：`light-primary` / `dark-primary` 与对应 `on-primary` 构成发送主按钮；悬停使用正文色与阅读面色。
- **键盘焦点**：`light-focus` / `dark-focus` 用于可交互元素的可见轮廓，具体线宽见 sidecar。

### Neutral

- **面板底色**：`light-bg` / `dark-bg` 承担品牌区、上下文与操作区。
- **连续阅读面**：`light-surface` / `dark-surface` 用于消息和字段；不为每条回答附加卡片。
- **正文与辅助文字**：`ink` / `muted` 分别承担主要内容与说明、角色、状态，禁用态仍采用可读的辅助色。
- **细线与控件边缘**：`line` 划分区域；`control` 提供输入、起始问题按钮与选文容器的可见边缘，不互相替代。
- **操作反馈与选文**：`hover` 对应悬停/按下；`selected` 对应原文选区上下文和文字选择。

### State colors

- **失败**：`danger` 配合 `error-bg`，同时显示未完成、保留内容与恢复说明。
- **PDF 临时定位**：`evidence-highlight` 仅用于 Reader 内唯一匹配原句的临时矩形高亮，不作为界面装饰色。

**The Evidence Color Rule.** 证据链接、选文与键盘焦点使用对应语义颜色；失败有独立文字和底色，不以颜色单独传达状态。

## Typography

**Brand Font:** frontmatter 的 `title`；Bahnschrift，回退 Avenir Next 与 sans-serif。
**Body Font:** `body` / `label`；Aptos，依次回退 Segoe UI Variable Text、PingFang SC、Microsoft YaHei UI 与 sans-serif。
**Code Font:** `code`；Cascadia Code，回退 Consolas 与 monospace。

全部使用本地可用字体，无远程字体请求。字标有明确几何感，界面与中文正文保持桌面工具的易读密度；等宽字体只服务代码。字号与字重以 frontmatter 为准。

### Hierarchy

- **Title**：侧栏首行 Kinbo 字标；不扩展为营销式 Display。
- **Body**：问题输入、按钮、消息正文；表格数字采用等宽数字特性。
- **Label**：角色、说明、状态、页码与设置标签；角色标签使用中等字重（500）。
- **Message heading**：回答内的小标题；空状态标题使用 `empty-title`，当前论文标题保持正文级大小与更紧的行高（1.5）。
- **Code**：代码块允许换行与任意长单词断行，不靠横向滚动保持完整内容。

**The One Brand Rule.** Kinbo 字标只占侧栏首行；正文角色名负责辨认回答者，不再重复堆叠品牌标题。

## Layout

### 当前侧栏结构

1. **品牌与工具**：Kinbo 书页 K 标记、字标、论文对话说明，以及移到另一侧、清空、关闭。清空使用面板内确认行。
2. **当前论文**：标题最多显示两行，完整标题可由 title 查看；其下说明完整文字层与本机历史。
3. **对话阅读区**：占剩余高度，连续消息按角色与分隔线排版，容纳页码、折叠推理与真实联网来源。
4. **提问区**：选文上下文、可见问题标签、问题框、联网、发送/停止、快捷键说明。
5. **模型与设置**：默认折叠，摘要显示当前模型；展开后单列安排接入方式、登录/API、模型、思考强度、回答要求与输入说明。
6. **状态**：底部独立短句，不把整段流式回答放进不断播报的 live region。

### 密度与窄窗口

侧栏默认宽度（336px），可在 host 中收缩，最大宽度（48%）；最小宽度表达式为 `min(264px, 48%)`，因此很窄的 host 可继续收缩，不能将 264px 写成绝对下限。左侧模式只交换与 PDF 相邻的分界边。

基本区域内距使用 `spacing.region`。品牌区垂直内距使用 `spacing.control`；消息上下内距使用 `spacing.message`，空状态使用 `spacing.empty`；相邻控件与文字间距按 `compact` / `control` 取值。无需发明新的全局间距级。

侧栏自身的 container 宽度不超过（300px）时，主要区域水平内距改为 `spacing.control`，隐藏「论文对话」副标与快捷键说明，动作间距收紧为 `spacing.compact`。这不是整个应用视口的媒体断点。长标题、选文、链接、正文和代码均可换行。

阅读区独立滚动且保留最小高度（80px）；操作区可滚动且最大占侧栏高度（60%）。选文原句超过可见高度（88px）后内部滚动。问题框最小高度（72px）、最大高度（200px），可垂直调整；其他多行字段最小高度（64px）。

### 主题与验证边界

显式的 Zotero `data-theme`、`data-color-scheme` 或 `color-scheme` 优先；未指定浅深色时跟随系统。属性变化即时更新，关闭时解除观察；独立预览的手动主题切换不写生产偏好。

本轮预览矩阵包含视口（1440 / 768 / 390px）与约（264px）侧栏的合成场景。它用于响应式与状态检查，不代表移动 Zotero 支持或真实模型质量。视觉文档的提取依据为正式 CSS 与组件/控制器源码；独立 finish review 的两项 material 修复已复核通过，其 verdict 只覆盖所复核问题，不替代全产品验收。

## Elevation & Depth

无 box-shadow。阅读面、面板底色、细线和明确边缘构成层级；选文容器与失败块有功能性的底色，消息没有气泡式外壳。控件 hover/press 只改变已有语义底色。

**The Flat Reading Rule.** 阅读面以底色和细线区分，不使用阴影、装饰渐变或浮动贴片制造层级。

## Shapes

控件采用克制圆角，按钮、常规字段、选文、代码与失败块使用 `rounded.control`，问题框使用 `rounded.input`。分界线与字段边缘均为细线（1px）。图标采用单色线性 SVG，常规视图图标（16px），品牌标记（20px），线宽（1.5px），圆端点与圆连接；菜单资源保持同一笔画语言。

## Components

### Buttons and toolbar

发送是唯一填充主按钮；普通操作与停止生成采用中性透明按钮。桌面最小高度（32px），图标按钮同宽；粗指针下按钮和折叠摘要最小高度提升为（44px），图标按钮宽度同步提升。默认、悬停、按下、禁用与深色变体由 frontmatter 颜色映射与 sidecar 示例记录。

所有可交互元素的键盘焦点为清楚的轮廓（2px，偏移 2px）。按钮仅对背景与文字颜色使用短反馈（150ms，CSS 默认 ease）；`prefers-reduced-motion` 下去除过渡。无加载旋转器、骨架屏、入场或装饰动画。

生成中隐藏发送并显示「停止生成」；清空与模型字段禁用，联网与思考强度还受接入方式限制。停止沿用现有 cancel 行为；关闭侧栏并不等于停止任务。关闭恢复到开启面板前的 Reader/工具入口焦点。清空先显示「清空本篇历史」和取消，取消后返回清空按钮。

### Inputs and settings

字段有可见标签、独立控件边缘、完整 placeholder 和统一焦点，不以 placeholder 代替标签。模型设置保留原生 select、input、datalist、details 语义。API 模式下联网不可用并解释原因；选择与加载模型不自动生成。

XHTML 控件使用 Zotero chrome 样式提供的 `no-native` 外观退出属性，避免宿主焦点渐变覆盖 Kinbo 的背景与边缘；按钮显式使用语义文字色和 `appearance: none`。保留原生字段语义与键盘行为。

Ctrl+Enter / Cmd+Enter 发送，输入法组合期间不发送；正常换行继续保留。发送失败保留输入，初始化失败可「重新连接」。

### Messages and feedback

消息显示「你」或「Kinbo」，回答按段落与小标题阅读，推理摘要与模型设置逐步展开。忙碌以「正在回答 · 可停止生成」说明；未完成内容与错误同存，不清空已有回答。独立 `role=status` 提供连接、整页读取、取消、定位与恢复反馈；消息区用 `aria-busy` 描述生成状态。

空状态只提供一个填入问题框的起始问题，不自动发送。恢复已有历史沿用会话接口。更新消息时仅在用户靠近底部（90px 内）或首次渲染时滚动到底部，阅读旧消息不被强行拖走。

### Evidence and selection

页码链接以下划线与证据色同时辨认，支持键盘访问。选文容器显示物理页码、完整原句和有名称的移除按钮；选文只进入上下文，不自动提交。原句在指定页唯一匹配时临时高亮（5 秒）；否则只跳页并说明需核对。只有真实返回的 sources 才显示联网来源，外链限制安全协议。

### Native menus

右键 Kinbo 子菜单保留前四项上游翻译操作；分隔后的增强区只留一个「深度阅读 / 停止阅读」入口，图标随当前论文的任务状态切换，点击时重新核对任务状态。论文对话、模型登录和后台更新管理位于 Zotero Tools 菜单，入口配套单色小图标。菜单由 Zotero 原生控件绘制，不将侧栏圆角或字体强加给宿主菜单。

## Do's and Don'ts

### Do:

- **Do** 复用已提取的浅深色语义配对；新增表面先核对既有源码与本文件。
- **Do** 保留清楚的角色、物理页码、字段标签与独立状态反馈。
- **Do** 在窄侧栏、低高度、键盘操作和深色模式下核对发送、停止与取消是否可达。
- **Do** 用自然中文直接命名动作，错误说明恢复路径与已有内容是否保留。

### Don't:

- **Don't** 把后续首选项、API 编辑器、翻译与品牌资源迁移描述为本阶段已交付。
- **Don't** 引入营销式大标题、聊天气泡墙、装饰性等宽标签或密集大写。
- **Don't** 添加阴影、装饰渐变、入场、悬浮、呼吸或大范围动画。
- **Don't** 以视觉工作改变完整输入、后台 API、数据格式、插件 ID、版本或更新通道；后台控制页不在本轮范围内。
- **Don't** 将合成预览、模拟接口或局部 finish 复核写成真实模型质量与全产品验收。
