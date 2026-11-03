# Kinbo

<!-- impeccable:product-schema 1 -->

## Platform

web

界面运行于 Zotero 桌面插件的 XHTML/Gecko 环境；独立 HTML 仅用于设计预览。不是一个新的浏览器应用。

## Users

在 Zotero 中阅读 PDF、翻译正文、核对证据、生成深度阅读笔记并向论文提问的科研用户。

## Product Purpose

在保留论文阅读空间的同时，让翻译、完整论文阅读、原文证据与 AI 对话形成连续工作流。

## Operating Context

Python 后台、翻译引擎、Codex 登录和 API 配置已经存在。插件通过本地后台管理论文会话，深度阅读完成后在父条目下保存子笔记。用户确认论文对话默认采用约 336px 的紧凑侧栏。

## Capabilities and Constraints

- 保留完整 PDF/全部页面输入、现有请求协议、会话和数据格式。
- 打开侧栏、选文、读取模型列表不发起模型生成；发送问题才调用模型。
- 引用以物理页码定位，原句唯一匹配才临时高亮；扫描页需要 OCR。
- 本阶段只改 Zotero 内论文对话，后台 Web 控制页原样保留。
- 插件 ID、设置命名空间、发布版本和更新通道本阶段保持不变。

## Brand Commitments

名称 Kinbo；专业、精致、克制；参考 Linear 的秩序与 Raycast 的操作效率，兼容 Zotero 原生习惯。说明采用直接、自然的中文。

## Evidence on Hand

仓库有可校验的上游 XPI、独立实现的对话与阅读桥接代码、模拟 Reader 测试和隔离 Zotero 集成测试。预览只使用合成论文与演示对话，不能视为模型质量证据。

## Product Principles

阅读空间优先；证据始终可回到原文；操作与计费边界清楚；失败保留已有内容；插件停用后完整清理注入界面。
