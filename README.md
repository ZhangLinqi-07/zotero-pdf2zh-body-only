# Zotero PDF2zh Body Only

让 Zotero 中的 PDF 翻译自动跳过参考文献与附录，同时保留这些章节的原文页面。

本项目是 [Zotero PDF2zh](https://github.com/guaguastandup/zotero-pdf2zh) 的第三方本地服务增强包，适用于已经安装并能正常使用原插件的用户。先安装原插件与服务，再应用本补丁。它提供章节识别、交界页段落过滤、本地控制页开关、安装前检查和文件恢复。

## 下载与兼容范围

从 [Releases](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases) 下载名称以 zotero-pdf2zh-body-only 开头的 ZIP，解压后进入包含 install.py 的文件夹。

首个预览版本支持 Zotero PDF2zh 服务端 **4.1.7**、翻译引擎 **pdf2zh_next 2.9.0** 和 **BabelDOC 0.6.2**。原版安装文件可从 [上游 v4.1.7 发布页](https://github.com/guaguastandup/zotero-pdf2zh/releases/tag/v4.1.7) 获取。安装脚本需要 Python 3.10 或更新版本，原服务与翻译环境推荐沿用 Python 3.12。Windows 已验证完整模拟翻译流程，跨平台安装逻辑另有自动测试。

本包增强 Python 托管的翻译环境。独立 winexe 模式暂不支持。其他版本的兼容性尚未验证，安装器会检查版本与原始文件，遇到未知改动时先停止。

翻译引擎通常位于独立的托管虚拟环境，版本检查以那个环境为准。请先确认原版能够正常翻译。若 pdf2zh_next 2.9.0 因 bitstring 5 缺少 BitStream 而无法启动，可在翻译引擎的 Python 环境中安装兼容版本。这个处理对应 [bitstring 的版本迁移说明](https://bitstring.readthedocs.io/en/stable/upgrading_to_version_5.html)。

~~~console
"翻译引擎环境的Python可执行文件" -m pip install "bitstring>=4.3,<5"
~~~

## 安装

找到原版服务的目录，也就是同时包含 server.py、utils 和 config 的文件夹。在本包目录运行安装预览，将下面的目录占位符换成自己的实际路径。

~~~console
python install.py --server-dir "你的服务目录" --dry-run
~~~

确认预览中的目标目录正确后，再运行安装。

~~~console
python install.py --server-dir "你的服务目录"
~~~

安装器会备份需要修改的源文件，并在目标目录生成启动器。已有 API 配置、PDF 附件、翻译结果与缓存均保留。安装目录可以含空格，也可以放在其他磁盘，程序不依赖作者电脑的路径。

如果原服务使用专门的 Python 环境，可在安装时明确指定该环境的 Python 可执行文件。安装器也会尝试寻找服务旁的 .server-venv 或服务内的 .venv。

~~~console
python install.py --server-dir "你的服务目录" --server-python "原服务使用的Python可执行文件"
~~~

本包只提供章节处理功能。用户仍需在自己的 Zotero 中选择免费服务或填写自己的付费 API 配置，翻译费用取决于所选服务。

## 在 Zotero 中使用

在安装后的服务目录中运行启动器。请沿用能够运行原服务的 Python 环境。

~~~console
python run_body_only.py --server-dir "你的服务目录"
~~~

Windows 用户也可以双击目标服务目录中的 start-body-only.cmd，前提是 Python 命令已在 PATH 中。启动器使用独立端口，不会停止已有服务，日志位于服务目录中的 body-only-logs。

打开 Zotero 的 PDF2zh 设置，将 Python 服务器地址设为 **http://127.0.0.1:8891**，翻译引擎选择 **pdf2zh_next**。之后照常右键原始 PDF，选择翻译 PDF 或双语对照。

浏览器打开 **http://127.0.0.1:8891/**，页面上方有自动跳过参考文献与附录开关，默认开启。开关保存后对之后发起的任务生效。关闭后沿用原有的完整翻译范围。页面也会显示最近一次识别的章节与页数。

端口已被占用时可另选一个端口，并在 Zotero 中填写相同地址。

~~~console
python run_body_only.py --server-dir "你的服务目录" --port 8892
~~~

## 工作方式

程序先在本机识别 References、Bibliography、Works Cited、Appendix、Appendices、Supplementary Material、参考文献、附录等明确标题，再确定首个尾部章节的位置。标题之前的正文照常翻译，后面的段落和页面保留原文。双栏文档按栏的阅读顺序处理。

参考文献从页面中间开始时，前面的正文仍能翻译。完整尾页不进入翻译或自动术语提取，最后的 PDF 仍保留这些原始页面。章节识别本身不调用语言模型，后续正文翻译仍使用用户配置的翻译服务。

识别到首个尾部章节后，后续所有内容均保留原文。这个规则适合正文之后接参考文献和附录的常见论文结构。若文献后还出现需要翻译的正文，建议关闭本功能。

## 识别边界

规则面向有文本层、章节标题清晰的论文。目录中的页码条目、正文中提到 Appendix 的句子，以及字体和位置不符合标题特征的文本，会尽量排除。没有把握识别时，保留原有翻译范围。

扫描件、旋转或特殊裁剪页面、只用字母标记的附录、罕见标题格式，可能无法识别。如果正文与文献被 PDF 合并为同一段落，程序优先保留正文，少量交界内容可能仍进入翻译。请检查最终译文，规则无法保证每篇论文都正确识别。

请关闭原插件的仅保留实际翻译页面选项，以便输出中保留原文尾页。原有跳过最后几页选项可以继续使用，程序采用两者中更小的翻译范围。

## 关闭与恢复

只想恢复全文翻译时，在本地控制页关闭开关即可。

需要恢复安装前的程序文件时，退出本增强版服务，在下载包目录运行恢复脚本。脚本保留备份，并在发现安装后又被修改的文件时停止，让用户先处理冲突。

~~~console
python restore.py --server-dir "你的服务目录"
~~~

上游更新可能覆盖本补丁。升级前可先恢复，待本项目发布支持新版本的增强包后再安装。请先阅读安装器报错，再决定是否使用显式覆盖选项。

## 测试

本地单元测试涵盖章节标题、同页正文与文献、双栏阅读顺序、异常后的内容恢复、开关保存，以及安装、重复安装、恢复和个人文件保留。

~~~console
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
~~~

完整翻译流程另使用本机模拟模型接口验证，参考文献和附录的标记没有进入模型请求，交界页正文正常翻译，输出保留全部页面。测试不会使用任何真实 API 密钥。可用已安装的 pdf2zh_next 环境运行集成测试。

~~~console
python tests/integration_local.py
~~~

## 上游与许可证

上游 Zotero 插件和服务由 guaguastandup 及其贡献者开发，本项目在其 4.1.7 源码基础上加入正文翻译过滤功能。项目与上游保持独立，详细来源和修改日期见 [NOTICE.md](NOTICE.md)。

代码沿用 **GNU AGPL v3**，完整文本见 [LICENSE](LICENSE)。BabelDOC、pdf2zh_next、模型和其他依赖由各自项目维护。本仓库不分发模型权重、论文、用户环境文件、API 密钥或本地翻译缓存。
