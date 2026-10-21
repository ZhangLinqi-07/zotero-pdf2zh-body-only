# 来源与修改说明

本项目包含 Zotero PDF2zh v4.1.7 的服务端派生代码，原项目由 guaguastandup 及其贡献者开发，仓库地址为 https://github.com/guaguastandup/zotero-pdf2zh 。

upstream 目录保存原版 server.py、index.html 与 utils/execute.py，用于明确修改基线和校验安装兼容性。这些文件与上游 v4.1.7 标签逐字节规范化比对一致，原有作者标记保留。

payload 目录包含修改后的服务文件，以及新加入的章节识别和运行时过滤模块。ZhangLinqi-07 于 2026 年 10 月 21 日整理本增强版本，新增章节跳过、本地控制页、可移植安装器、启动器、恢复器与测试。修改后的服务源码不代表上游官方发布。

本项目依据 GNU Affero General Public License version 3 发布，许可证文本见 LICENSE。原程序、原作者和其他依赖的权利与声明继续适用。

pdf2zh_next 与 BabelDOC 是独立安装的依赖，其源代码分别可在 https://github.com/PDFMathTranslate/PDFMathTranslate-next 和 https://github.com/funstory-ai/BabelDOC 获取。本包不包含这些依赖的模型权重或运行环境。
