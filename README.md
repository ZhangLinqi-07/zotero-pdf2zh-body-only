# Kinbo

**在 Zotero 中完成 PDF 翻译、论文深度阅读与 AI 论文对话。**

[![Release](https://img.shields.io/github/v/release/ZhangLinqi-07/zotero-pdf2zh-body-only?label=Kinbo)](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases/latest)
[![GitHub Stars](https://img.shields.io/github/stars/ZhangLinqi-07/zotero-pdf2zh-body-only?style=flat&label=Stars)](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/stargazers)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

Kinbo 是一个面向科研阅读的 Zotero 工具。翻译正文、追问一段原文、理解整篇论文，再把阅读结果留在论文条目下，让原文、证据、对话和笔记保持联系。

[下载 Kinbo](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases/latest) · [安装与更新](#安装与更新) · [开始使用](#开始使用) · [本版更新](CHANGELOG.md) · [反馈问题](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/issues)

## Kinbo 能做什么

### 翻译论文，保留阅读线索

在 Zotero 中直接翻译 PDF，生成译文和双语对照。可按设置跳过参考文献与附录，保留原始页面、双栏和数学公式；正文排不下时使用完整译文续页。明显空译、原文照返和长段英文残留会经过检测与一次补译，仍不完整时明确报错。

表格文字会参与正文检查。扫描页、图片里的文字和复杂 PDF 仍受 OCR、文档解析与模型能力限制，检测不能替代逐句校对。

### 在论文旁提问，并返回证据

阅读器中的 Kinbo 对话侧栏默认宽 336px，可放在左侧或右侧。支持浅色、深色和窄窗口；选文进入提问上下文，模型配置按需展开，尽量为 PDF 留出空间。

对话使用论文的完整文字层，历史保存在本机。回答中的物理页码引用可跳转；原句在指定页唯一匹配时，显示临时高亮。选文不会替代整篇论文输入。没有文字层的扫描页、图像内部内容需要先做 OCR。

### 深度阅读完整论文，归档为子笔记

把原始 PDF 或全部页面图像与完整阅读模板交给所选模型，结合实际联网检索取得的来源，梳理论文问题、方法、公式、实验、局限与后续方向。输入不会静默改为选页或本地分段摘要。

达到服务商单次输出上限时保留已有内容并续写。完成后，结果直接保存为原论文父条目下可编辑的 Zotero 子笔记，保留来源、表格与原生 LaTeX 公式。关闭 Zotero 后的结果可在重新打开时补存；归档重试不会覆盖已编辑的笔记。

## 安装与更新

当前正式版本为 **Kinbo 0.4.6**，配套 Zotero 插件 **4.1.7.18**。本轮原生安装与 Reader 验收环境为 Windows、Zotero 10.0.7；安装清单兼容上限为 Zotero 10.0.*，其他版本未逐一完成原生验收。

| 你的情况 | 使用入口 |
| --- | --- |
| 第一次安装，Windows x64 或 macOS | [完整安装包 ZIP](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases/download/v0.4.6/zotero-pdf2zh-body-only-v0.4.6.zip) |
| 已有 Kinbo 后台，只需安装或覆盖插件 | [Zotero 插件 XPI](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases/download/v0.4.6/zotero-pdf2zh-body-only-v0.4.6.xpi) |
| 已安装可自动更新的 Kinbo | Zotero「工具 → 插件 → 齿轮 → 检查更新」 |
| 版本说明与下载校验 | [Release](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases/tag/v0.4.6)、SHA256SUMS.txt |

### Windows 首次安装

1. 安装 Zotero，下载完整 ZIP，解压到准备长期保留的文件夹。
2. 双击 install-windows.cmd。安装器会校验下载资源、准备独立 Python 3.12 环境并安装翻译引擎，无需预先手动安装 Python。
3. 在 Zotero「工具 → 插件」中选择「从文件安装插件」，安装 app 文件夹中的 zotero-pdf2zh-body-only.xpi。插件管理器显示名称为 **Kinbo**。
4. 在现有翻译设置页中确认后台地址。新安装默认地址为 **http://127.0.0.1:8891**，翻译引擎选 pdf2zh_next；已有安装继续使用自己的端口。
5. 选择免费翻译服务，或配置自己的模型 API / Codex 登录。随后从论文右键菜单或 PDF 阅读器开始使用。

翻译设置页当前仍沿用 PDF2zh 名称，是兼容现有配置的入口。安装器下载所需组件，首次翻译还可能下载字体与文档分析模型；请保留安装目录，安装或翻译过程中不要移动它。

Windows 本机后台首次启动会为当前用户配置静默登录启动。需要手动启动时，运行 app/start-body-only.cmd。浏览器打开后台地址，可使用完整 Web 控制页；本版保留它原有的设计与功能。

若 Python 包下载较慢，可在解压目录使用镜像：

```console
install-windows.cmd --index-url https://mirrors.ustc.edu.cn/pypi/simple
```

### 已有用户更新

后台 **0.4.1 及更新版本**可以通过 Zotero 检查插件更新获得正式 XPI。插件携带配套后台源码包，会在翻译、阅读和对话任务空闲后校验、备份、同步及重启；启动检查失败时恢复旧版源码。API 配置、论文、译文、阅读历史、Zotero 笔记和 Python 环境保留。

打开论文对话、深度阅读或模型设置时，会先检查后台连接。Windows 尝试唤醒已有的 Kinbo 计划任务；macOS 自动唤醒已关联后台，首次无法找到原安装位置时可在 Zotero 中选择包含 server.py 的原后台文件夹，关联后配置登录自动启动。端口沿用当前设置，不需要输入启动命令或重新填写 API。远程 / HTTPS 后台、未安装后台、修改过的受管理源码或依赖范围不匹配时，会提示相应处理方式。

后台 **0.3.x / 0.4.0pre1** 需要先完成一次迁移：下载本版 ZIP，等待活动任务结束并停止原后台，使用原服务的 Python 对原目录安装，再运行原启动器。

```console
python install.py --server-dir "原后台目录" --force
```

缺少有效更新地址的早期插件也需手动覆盖安装本版 XPI。无需先卸载插件或删除已有配置。源码推送本身不会触发升级；只有正式 Release 和更新清单完成发布后，检查更新才会提供新版。

### macOS 首次安装

1. 下载上方完整 ZIP 并解压，双击 install-macos.command，按系统提示允许运行。
2. 安装器支持 Apple Silicon 和 Intel Mac，自动校验下载工具并准备独立 Python 3.12，无需预装 Python 或输入命令。
3. 后台放在 ~/Library/Application Support/Kinbo/app。安装器等待服务就绪后打开 Zotero，并在 Finder 中选中 XPI；在 Zotero「工具 → 插件 → 从文件安装」中安装它。
4. 首次安装的后台地址为 http://127.0.0.1:8891。在 Zotero 中配置模型后即可使用；以后登录自动启动。

已有后台的用户优先更新 XPI，并从 Zotero 的连接提示中关联原后台目录，以保留原 Python 环境、端口与 API。系统登录项若禁用了 Kinbo，需要重新允许后台运行。后台是独立服务，关闭 Zotero 不会中断正在执行的翻译或阅读。

### Linux 与已有 Python 环境

也可使用 Python 安装入口。创建全新环境时，需要 Python 3.10+ 和 uv，安装器会另外准备 Python 3.12：

```console
python setup_fresh.py --install-dir "新的安装目录" --start
```

已有可运行服务，可先预览再安装，并按需指定原服务 Python：

```console
python install.py --server-dir "原后台目录" --dry-run
python install.py --server-dir "原后台目录" --server-python "原服务的Python可执行文件"
```

不要把这些命令指向不相关的个人目录。当前依赖范围以 [compatibility.json](compatibility.json) 为准：服务组件 4.1.7、pdf2zh_next 2.9.0、BabelDOC 0.6.2、bitstring>=4.3,<5。独立 winexe 运行方式尚未适配。

## 开始使用

### PDF 翻译与双语对照

右键论文或 PDF，打开 **Kinbo** 菜单，选择翻译或双语对照。参考文献、附录及排版选项可在本地 Web 控制页调整。已有翻译 API 继续使用，不需要为深度阅读再维护另一套密钥。

### 论文对话

打开 PDF，点击阅读器工具栏的 **Kinbo 对话**，或在 Zotero 工具菜单选择 **Kinbo 论文对话边栏**。

- 直接输入问题，使用 Ctrl+Enter / Cmd+Enter 发送。
- 选中原文后点击「向 Kinbo 提问」，核对页码与选文再发送。
- 在「模型与设置」中选择已有翻译 API 或 Codex，按需启用联网搜索、思考强度与回答要求。
- 生成中可停止；关闭侧栏不会取消后台生成，重新打开可恢复已有会话。

打开侧栏、选择原文、读取模型列表与检查登录不会发起模型生成。发送问题才调用所选服务。联网搜索当前供 Codex 对话使用，来源只依据真实返回的检索记录展示。

### 深度阅读与笔记

右键论文或 PDF，在 Kinbo 菜单中选择 **深度阅读**。同一篇任务运行时，该入口显示 **停止阅读**，用于请求停止后续续写并保留已有内容。

自动归档需要 PDF 已归属于论文父条目，且资料库可编辑。阅读进度在 Zotero 内显示；完成后可在父条目下查看子笔记。也可从本地 Web 页上传完整 PDF，查看阅读记录，下载 Markdown 或 HTML；网页上传没有 Zotero 归属信息时不会自动创建子笔记。

阅读模板位于源码的 [payload/prompts/deep_reading_zh.txt](payload/prompts/deep_reading_zh.txt)。模型和接口需要支持所选输入方式及实际搜索工具；未取得真实搜索证据时会明确失败，不把离线回答标为已联网。

### 模型与登录

Zotero 工具菜单中的 **Kinbo 模型后端与 Codex 登录**打开本地模型控制页。翻译、深度阅读和论文对话可按各自设置使用模型后端。

API 可复用 OpenAI 兼容接口、OpenAI、Gemini、DeepSeek 等已有配置；能翻译文本不代表接口能接收完整 PDF 或执行搜索。Codex 需要本机有可用程序并完成官方登录。Mac 会自动查找系统或用户“应用程序”文件夹内 Codex 桌面版自带的程序，无需另装 CLI；也支持单独安装的 CLI。安装后点“刷新登录与模型”。可用模型和额度由实际账号返回，Kinbo 不另存登录令牌，也不修改用户的 Codex 工程配置。使用现有翻译 API 无需安装或登录 Codex。

深度阅读接受最大 50 MB 的完整 PDF；全部页面图像模式按顺序渲染每一页，不静默截断。DeepSeek 官方图像模式另有 600 页、单页尺寸及序列化请求 48 MiB 检查。服务商仍可能限制文件、上下文和单次输出，超限会明确报错。

## 数据、费用与使用边界

对话、阅读记录与归档状态在本机保存；提问、翻译或深度阅读时，相关 PDF、文字、图像、提示词和上下文会交给你选择的模型服务。请按自己的数据要求选择服务与论文内容。

Kinbo 不提供公共模型额度。免费翻译服务可用于其支持的翻译任务；深度阅读需要自己的 API 或 Codex。实际费用和额度按所选平台计算，停止请求后当前已发出的调用仍可能产生费用。

深度阅读保留完整输入与中间结果，模型输出上限时续写，不自行设置固定输出 token 上限或思考预算。论文对话按所选模型提供思考强度选项。引用、高亮与来源记录帮助核对证据，不能替代对模型解释和原文的判断。

## 常见问题

**更新后出现 Kinbo / PDF2zh 两个菜单或旧阅读入口。** 0.4.5 修复了覆盖升级时的旧界面清理。安装新版后完全退出并重新打开 Zotero；正常情况下只显示一个 Kinbo 菜单，阅读区只保留「深度阅读 / 停止阅读」。

**检查更新显示没有新版。** 核对插件当前版本、更新地址和 Release 是否已完成发布。0.4.6 对应插件 4.1.7.18；仅拉取仓库源码不会替换已安装的 XPI。也可从本版 Release 手动覆盖安装。

**插件已更新，但后台无法连接。** 新版会先尝试自动恢复；Mac 首次可能提示关联原后台文件夹，选择包含 server.py 的目录即可。新安装默认 8891，已有用户可能使用 8892 等端口，需与后台一致。只有 XPI、尚未安装后台的电脑应先运行对应系统的完整安装器；远程服务需由服务器管理员启动。

**Codex 登录或联网阅读失败。** 先核对本机 CLI、官方登录状态，以及所选服务是否支持要求的工具。错误中的步骤和错误码可用于排查；不要在问题反馈中粘贴密钥、登录令牌、完整配置或私人论文。

**扫描论文或公式没有正确识别。** 论文对话依赖文字层，需要先做 OCR。完整页面图像阅读可处理视觉内容，但细小公式、图片文字和图表理解仍受模型能力限制。

**为什么仓库和文件名仍有 pdf2zh？** 产品名称与维护方向是 Kinbo。仓库地址、插件 ID、配置键和部分安装资源名暂时保留，以便已有用户原位升级；使用相同插件 ID 的安装不能并存。来源和许可证见文末。

## 开发与验证

```text
plugin/       Zotero 桥接、Reader 适配、对话视图、样式与笔记渲染
payload/      本地后台、Web 控制页、模型与翻译运行模块
scripts/      校验清单、后台源码包与正式发布工具
upstream/     安装校验及恢复使用的固定组件基线
tests/       模拟接口、安装、更新、PDF 与 Reader 验证
```

设计与扩展：[DESIGN.md](DESIGN.md)、[UI 架构与迁移计划](docs/kinbo-ui-architecture.md)、[独立 UI 预览](docs/ui/paper-chat-preview.html)、[UI 验证记录](docs/ui/validation.md)。预览需在下载源码后本地打开，使用合成内容，不连接后台。

安装测试依赖并执行基础检查：

```console
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
node tests/test_paper_chat_ui.js
node tests/test_note_format.js
node tests/test_reading_bridge.js
node tests/test_reading_backend_ui.js
node tests/test_backend_update.js
python tests/integration_backend_update.py
```

原生翻译与 PDF 排版集成需要对应引擎环境，见 tests/integration_local.py、tests/integration_layout.py；Zotero 原生 Reader 验证入口为 tests/integration_chat_reader.py，使用独立 profile、资料库和合成 PDF。缺少依赖而跳过的检查不计为通过。模拟模型测试不代表真实模型生成质量。

开发构建使用校验过的组件 XPI。正式发布同步 Kinbo 版本、插件版本与 payload 校验清单，执行配套发布工作流；安装包下载校验成功后才切换 updates.json，流程见 [.github/workflows/release.yml](.github/workflows/release.yml)。

## 开源组件与许可证

Kinbo 作为独立项目维护与发布，集成了开源翻译与 Zotero 组件。Zotero PDF2zh 的插件/服务代码来自 [guaguastandup/zotero-pdf2zh](https://github.com/guaguastandup/zotero-pdf2zh) 4.1.7；PDF 翻译依赖 [PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next) 与 [BabelDOC](https://github.com/funstory-ai/BabelDOC)。感谢这些项目及其贡献者。

阅读器论文对话与 Codex 连接由本项目独立实现，功能设计参考 [Zotero Paper AI Assistant](https://github.com/ddd3651/zotero-paper-AI-assistant) 的公开功能，未复制其源码。笔记渲染使用本地随包提供的 Marked、DOMPurify 与 MathJax，各自许可证随资源保留。

项目代码采用 **GNU AGPL v3**，见 [LICENSE](LICENSE)。来源、作者声明、修改记录与依赖说明见 [NOTICE.md](NOTICE.md)。不随仓库分发私人论文、个人配置、API 密钥或模型权重。

## 关注项目

[Star History](https://www.star-history.com/#ZhangLinqi-07/zotero-pdf2zh-body-only&Date) · [版本记录](CHANGELOG.md) · [问题反馈](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/issues)
