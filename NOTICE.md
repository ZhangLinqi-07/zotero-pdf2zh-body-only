# 来源与修改说明

本项目包含 Zotero PDF2zh v4.1.7 的服务端派生代码，原项目由 guaguastandup 及其贡献者开发，仓库地址为 https://github.com/guaguastandup/zotero-pdf2zh 。

upstream 目录保存原版 server.py、index.html、utils/execute.py 与 utils/environment_lifecycle.py，用于明确修改基线和校验安装兼容性。这些文件与上游 v4.1.7 标签逐字节规范化比对一致，原有作者标记保留。

payload 目录包含修改后的服务文件，以及新加入的章节识别和运行时过滤模块。ZhangLinqi-07 于 2026 年 10 月 21 日整理本增强版本，新增章节跳过、本地控制页、可移植安装器、启动器、恢复器与测试。修改后的服务源码不代表上游官方发布。

本项目依据 GNU Affero General Public License version 3 发布，许可证文本见 LICENSE。原程序、原作者和其他依赖的权利与声明继续适用。

v0.2.0 新增从空目录安装的引导程序。原版服务与 XPI 从 guaguastandup/zotero-pdf2zh 的 v4.1.7 发布页下载，XPI 不作修改，对应完整源代码可从 https://github.com/guaguastandup/zotero-pdf2zh/tree/v4.1.7 获取。uv 从 astral-sh/uv 的 0.13.4 发布页下载，源代码、MIT 和 Apache-2.0 许可证见 https://github.com/astral-sh/uv/tree/0.13.4 。下载内容不提交到本源码仓库。

v0.3.0 加入深度阅读、共享翻译 API、公式保护、双栏整页对照和 Zotero 右键桥接。ZhangLinqi-07 于 2026 年 10 月 21 日修改服务和 bootstrap.js，并新增可读的 plugin/body_only_bridge.js。build_plugin.py 根据校验过的上游 XPI 构建增强 XPI，上游主体脚本保留，新增桥接源码直接包含在增强 XPI 内。原版 XPI 继续保留。

v0.3.1 增加阅读结果自动保存为 Zotero 子笔记、原生 LaTeX 公式与归档重试，并将右键菜单显示名改为 Kinbo。新增 plugin/reading_note.js，增强 XPI 内包含相应源码及 Marked、DOMPurify 与许可证。

prompts/deep_reading_zh.txt 是维护者提供的阅读模板。笔记渲染使用 Marked 18.1.1、DOMPurify 3.4.17 和 MathJax 3.2.2，原许可证与版本校验清单保存在 payload/web/vendor。Marked 采用 MIT，DOMPurify 提供 Apache-2.0 与 MPL-2.0，MathJax 采用 Apache-2.0，其作者声明继续适用。

pdf2zh_next 与 BabelDOC 是独立安装的依赖，其源代码分别可在 https://github.com/PDFMathTranslate/PDFMathTranslate-next 和 https://github.com/funstory-ai/BabelDOC 获取。本包不包含这些依赖的模型权重或运行环境。
