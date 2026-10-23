# Zotero PDF2zh Body Only

[![GitHub Stars](https://img.shields.io/github/stars/ZhangLinqi-07/zotero-pdf2zh-body-only?style=flat&logo=github&label=Stars)](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/stargazers)
[![README views](https://hits.sh/github.com/ZhangLinqi-07/zotero-pdf2zh-body-only.svg?label=README%20views&color=4f46e5)](https://hits.sh/github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/)

让 Zotero 中的 PDF 翻译自动跳过参考文献与附录，保留双栏和数学公式，并用同一 API 做深度结构化阅读。

本项目基于 [Zotero PDF2zh](https://github.com/guaguastandup/zotero-pdf2zh) 提供章节识别、深度阅读与版式保护。**新用户可以直接下载本仓库安装，无需预先安装原版服务。** Kinbo 深度阅读支持完整 PDF 或全部页面图像与提示词一次提交，达到接口输出上限后自动续写，完成后自动生成论文子笔记。已有原版的用户也可以使用增强补丁安装方式。

## Windows 新用户直接安装

先安装 Zotero。从 [Releases](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases) 下载 v0.3.6 或更新版本的 ZIP，完整解压到准备长期保留的文件夹，然后双击 **install-windows.cmd**。通过 GitHub 的 Code → Download ZIP 下载源码也能使用同一个入口。

安装器面向 Windows x64，会从官方发布地址下载并校验 uv、原版服务和原版 XPI，准备独立的 Python 3.12 环境，安装兼容的翻译引擎，再应用本项目的章节跳过功能。无需提前安装 Python 或手动配置环境变量。首次安装需要联网下载较多依赖，请等到安装完成提示出现。

安装完成后，本地服务会启动。到 Zotero 的插件管理窗口，使用从文件安装插件功能，选择生成在 **app** 文件夹中的 **zotero-pdf2zh-body-only.xpi**。增强 XPI 基于上游 4.1.7，版本标为 4.1.7.8，保留原插件 ID 与已有设置。原 PDF2zh 右键菜单显示为 Kinbo，深度阅读位于其子菜单内，原有双语对照继续使用同一入口。上游原版 XPI 也会保留在 app 目录。增强包使用本仓库的更新地址，提供明确的版本、兼容范围与下载校验，不会通过上游更新地址覆盖增强功能。后端服务仍通过本仓库安装包更新。

v0.3.4 及更早增强包缺少 Zotero 必填的更新地址字段，可能无法从 XPI 正常安装。遇到此问题请直接下载 v0.3.5 的 XPI，在 Zotero 插件管理窗口覆盖安装，无需卸载原插件或重新填写 API。旧包已安装者也需要手动安装这次修正版，之后插件可通过本仓库更新通道检查新版。

在 Zotero 的 PDF2zh 设置里，将 Python 服务器地址改成 **http://127.0.0.1:8891**，翻译引擎选择 **pdf2zh_next**，再选择免费服务或填写自己的 API。之后照常右键 PDF 进行翻译或生成双语对照。原版插件默认的 8890 地址需要手动改成这里的 8891。

以后双击 **app/start-body-only.cmd** 即可启动服务，翻译时保持启动窗口开启。浏览器打开 **http://127.0.0.1:8891/** 可以切换跳过参考文献与附录。请保留整个解压目录，安装后移动目录可能使虚拟环境中的路径失效。

首次翻译还可能下载 BabelDOC 的字体和文档分析模型，这些资源不包含在源码包中。安装失败时可以重新运行安装器，它会复用已校验的下载和已经创建的专用环境。翻译过程中请等待任务结束再重新运行安装器。

如果 Python 包下载较慢，可以在解压目录打开终端，明确选择中科大镜像。默认使用 PyPI。

~~~console
install-windows.cmd --index-url https://mirrors.ustc.edu.cn/pypi/simple
~~~

## 已有 Python 和 uv 的新用户

在空目录中安装服务，可直接运行下面的命令。执行 setup_fresh.py 的 Python 需要 3.10 或更新版本，安装器会另行准备运行服务所用的 Python 3.12。uv 可以从 [官方安装说明](https://docs.astral.sh/uv/getting-started/installation/) 获取。

~~~console
python setup_fresh.py --install-dir "你的新安装目录" --start
~~~

Windows 已验证新目录安装和运行流程。其他系统可以使用 Python 入口，跨平台安装逻辑有自动测试，完整翻译环境仍需自行确认。安装器拒绝向已有个人文件的非托管目录安装，已有原版服务请使用下文的 install.py。

## 下载与兼容范围

从 [Releases](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases) 下载名称以 zotero-pdf2zh-body-only 开头的 ZIP，解压后进入包含 install.py 的文件夹。

当前预览版本支持 Zotero PDF2zh 服务端 **4.1.7**、翻译引擎 **pdf2zh_next 2.9.0** 和 **BabelDOC 0.6.2**。新安装器自动锁定这些版本，并安装 **bitstring>=4.3,<5** 修复 BitStream 兼容问题。下载清单和 SHA256 保存在 [downloads.json](downloads.json)，上游来源为 [v4.1.7 发布页](https://github.com/guaguastandup/zotero-pdf2zh/releases/tag/v4.1.7)。

本包增强 Python 托管的翻译环境。独立 winexe 模式暂不支持。其他版本的兼容性尚未验证，安装器会检查版本与原始文件，遇到未知改动时先停止。

翻译引擎通常位于独立的托管虚拟环境，版本检查以那个环境为准。对已有原版的安装，请先确认原版能够正常翻译。若 pdf2zh_next 2.9.0 因 bitstring 5 缺少 BitStream 而无法启动，可在翻译引擎的 Python 环境中安装兼容版本。这个处理对应 [bitstring 的版本迁移说明](https://bitstring.readthedocs.io/en/stable/upgrading_to_version_5.html)。

~~~console
"翻译引擎环境的Python可执行文件" -m pip install "bitstring>=4.3,<5"
~~~

## 已有原版服务的补丁安装

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

免费翻译可以继续使用。深度阅读需要用户自己的 LLM API，并直接复用翻译配置，不会回退到公共免费翻译接口。本项目不提供作者的 API 额度。

## 深度结构化阅读

在 Zotero 右键论文或 PDF，在 Kinbo 子菜单中选择深度结构化阅读。增强插件直接读取 PDF、同步当前启用的翻译 API 配置并开始阅读，在 Zotero 内显示进度，完成后自动创建子笔记，无需跳转网页。点击该菜单即授权本次模型请求，会消耗自己的 API 额度。重复点击同一篇正在阅读的 PDF 会复用进行中的任务。

阅读完成后，插件自动创建可编辑的 Zotero 子笔记，挂在最初选择的论文父条目下。标题、段落、表格、来源记录与原生 LaTeX 公式一起保存。期间切换选中的论文不会改变归属，PDF 附件也不会被改写。暂时关闭 Zotero 时，已生成结果留在本地服务，重新打开后自动补存。保存重试会查找同一次阅读的已有笔记，避免重复创建，也不会覆盖用户编辑后的笔记。归档过程不调用模型。

页面显示等待保存、保存成功或待重试状态。模型输出未完成时，子笔记保留显著的未完成说明。独立 PDF 需要先在 Zotero 创建父条目，且资料库必须允许编辑。直接在网页上传的 PDF 没有 Zotero 归属信息，仍可下载 Markdown 与 HTML，自动归档应从 Zotero 右键入口发起。

网页控制页仍可单独使用，选择本机 PDF 或服务目录中的 PDF 后点击开始。若之前已用 API 翻译过，页面会读取服务端保存的同一份配置，无需重新填写密钥。首次在 Zotero 配置 API 后，即使尚未进行收费翻译，也可通过右键入口同步配置并直接阅读。Zotero 和网页使用同一套完整 PDF 阅读流程与价格设置。

共享配置可识别 OpenAI 兼容 API、OpenAI、Gemini、DeepSeek、SiliconFlow API、ModelScope、智谱、Grok 和 Groq。实际阅读还要求所选模型和接口支持 PDF 文件输入，纯文本翻译接口无法直接读取 PDF。OpenAI 兼容中转平台使用后台给出的地址和完整模型名。只有免费翻译服务时，需先配置自己的接口。

页面里的共享 API 配置会写入翻译使用的 config.toml，已有的其他翻译设置保留。接口地址、模型与已配置状态可以展示，密钥不会通过配置查询接口返回，也不写入浏览器本地存储。

阅读模板保存在 prompts/deep_reading_zh.txt，内容来自本项目维护者提供的论文深度阅读提示词。笔记覆盖论文信息、研究问题、方法与公式、实验、图表、局限、未来方向和总结。理论论文按证明、假设与边界调整内容，不机械填补实验栏目。

每次深度阅读先联网检索论文身份、发表状态和外部资料，优先使用出版社、会议、期刊和作者机构的官方页面。默认复用当前阅读 API，Gemini 使用 Google Search，OpenAI 兼容服务使用 Responses web_search，DeepSeek 官方使用独立 Search API。也可在阅读选项中选择另一套已有的翻译 API 负责检索，无需另建密钥存储。接口未提供真实搜索记录与有效网页来源时明确失败，不自动退回离线阅读，也不自动重复收费调用。工具支持情况取决于服务商和模型。

检索结果与原始 PDF、完整提示词一起交给阅读模型。论文不在本地切分、摘录或先生成摘要，图表、公式与扫描页交给支持 PDF 的模型解析。笔记区分 PDF 证据和外部证据，自动保存工具返回的来源链接、检索时间与检索用量。信息无法核实时仍须标为未核实。Gemini 和 Responses 的阅读请求也保留原生搜索工具，续写期间取得的新来源一并保存。

阅读选项提供自动、完整原始 PDF、全部页面图像三种输入模式。自动模式下，DeepSeek 官方 `deepseek-flash` 使用全部页面图像，其余 API 使用原始 PDF。图像模式将每一页渲染为 144 dpi 整页 PNG，保留页码顺序，与完整提示词一次提交，不选页或分段摘要。每次续写仍携带全部页面和已有对话。笔记会标明实际输入方式和页数，图像中的细小公式识别受模型视觉能力影响。

DeepSeek 官方不接受 PDF 文件输入，但 Flash 支持图像，见 [DeepSeek 视觉文档](https://api-docs.deepseek.com/guides/vision/)。搜索使用同一密钥的 Search API，Flash 阅读请求不携带它会忽略的原生 web_search 工具。插件不会替换用户选择的模型。官方图像模式最多 600 页，并检查单页尺寸及序列化请求的 48 MiB 限制。超限时明确停止，未通过本机预检时不会调用搜索或阅读 API。若搜索证据或续写历史使完整请求超限，则该阅读请求不会发送，已有笔记保留。上下文超限和服务商拒绝输入也会明确失败。

Gemini 模型自动使用原生 generateContent，OpenAI 官方自动使用 Responses，其他模型默认使用 Chat Completions，也可手动选择协议。原始 PDF 输入说明见 [Gemini 文档](https://ai.google.dev/gemini-api/docs/generate-content/document-processing) 与 [OpenAI 文档](https://developers.openai.com/api/docs/guides/file-inputs)。中转接口不支持所选格式时明确失败，不会退回文本摘要。Zotero 中的启动错误会显示具体的本地校验原因，原始 HTTP 异常及凭据不会展示。

升级至 v0.3.6 时需要同时更新增强后台和 XPI，并重新启动后台。已有翻译 API 与 Zotero 资料库不需要重新配置。只安装新 XPI 而继续运行旧后台，会得到明确的后台版本提示。

翻译引擎完成模型阶段后会检查识别到的较长英文正文，检测空译文、原文照返和中文译文中残留的长英文句子，对异常段落绕过旧缓存补译一次，并保留公式占位符。补译仍失败则记录页码并使任务失败，避免把整段英文当作已完成译文。参考文献和附录按原有跳过设置处理。此检查针对明显漏译，不能代替逐句语义校对，也无法覆盖 PDF 解析阶段完全没有识别出的文字。

插件不发送输出 token 上限、思考预算或思考强度参数，旧版分段和 token 设置不再生效。网络等待默认不设置超时，可自行指定秒数。模型与平台自身仍有文件大小、上下文和单次输出边界，本地接受的 PDF 最大为 50 MB。

达到平台单次输出上限后，插件在保留完整 PDF 和已有输出的对话中自动接续，直到接口正常完成，不设置固定续写次数。Gemini 原生思考签名按原样保留，重复的边界文字会合并。每次返回都保存检查点，后续失败、服务重启或手动停止时保留已有笔记并明确标记未完成，避免重复输出造成无效循环。Kinbo 菜单和网页提供停止后续续写，当前已发出的请求结束后停止新增调用。API 自身拒绝过长输入或持续无法生成正文时，无法保证得到完整笔记。

笔记可下载 Markdown，也可导出公式已经排版的离线 HTML。界面分别展示阅读与检索的 API 请求次数和 token 用量，Gemini 的输出统计包含接口报告的思考 token。续写会产生额外调用，各轮输入与输出均计入统计。填写阅读服务商单价和自己的充值比例后，可估算阅读生成的 token 部分费用，检索阶段与搜索工具费用另计，整篇总费用以服务商账单为准。

## 公式与双栏保护

控制页默认开启保留双栏。原文和译文以完整页面左右并排，原文在左，译文在右，每一半都保留原有双栏。原来的裁剪对照入口也会改走整页对照，避免把论文拆成单栏。需要手机裁剪模式时，可以关闭保留双栏选项。

公式保护默认自动识别。对于密集数学、金融和经济论文，可以选择公式优先，保留公式较多的段落及其原有位置。这个模式可能让夹杂公式的整段文字继续保持英文。普通排版选项可关闭额外公式保护。

实现保留分数线等绘图元素，补充 Cambria Math 字体识别，限制文本跨越原栏间距，避免单个过长译文把整篇字号一起缩小。公式周围的说明文字继续翻译。原栏内无法安全容纳的完整译文会进入紧随该页的双栏译文续页，正文编号可点击跳转。续页保留完整模型译文，并以原 PDF 的公式图像呈现其中的公式。排版失败不会用英文原文代替译文。极端版式、扫描件和错误的公式识别仍需检查。

## 在 Zotero 中使用

在安装后的服务目录中运行启动器。请沿用能够运行原服务的 Python 环境。

~~~console
python run_body_only.py --server-dir "你的服务目录"
~~~

Windows 用户也可以双击目标服务目录中的 start-body-only.cmd，脚本会调用安装时选定的 Python。启动器使用独立端口，日志位于服务目录中的 body-only-logs。

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

已有 v0.1.0 或 v0.2.0 增强包的用户，退出旧服务后，先用 restore.py 恢复原文件，再用新版 install.py 安装，并安装新的增强 XPI。个人 API 配置与翻译结果不参与恢复。若旧服务仍占着端口，新启动器会提示退出旧窗口或改用其他端口。上游更新可能覆盖本补丁，升级前可先恢复，待本项目发布支持新版本的增强包后再安装。

## 测试

本地单元测试涵盖章节标题、同页正文与文献、双栏阅读顺序、异常后的内容恢复、开关保存，以及安装、重复安装、恢复和个人文件保留。新安装器另有下载校验、ZIP 路径检查、个人目录保护、新安装与重试测试。

~~~console
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
~~~

完整翻译流程另使用本机模拟模型接口验证，参考文献和附录的标记没有进入模型请求，交界页正文正常翻译，输出保留全部页面。测试不会使用任何真实 API 密钥。可用已安装的 pdf2zh_next 环境运行集成测试。

~~~console
python tests/integration_local.py
~~~

数学双栏集成测试使用本地模拟模型，比较六处公式区域的像素、完整并排宽度和过长译文续页的完整结尾。Windows 默认使用本机的 Cambria Math 测试字体，其他系统可通过参数提供已安装的数学字体。

~~~console
python tests/integration_layout.py --font "本机数学字体文件" --font-number 0
~~~

浏览器使用本地 vendored Marked、DOMPurify 和 MathJax 渲染笔记，渲染时无需访问外部脚本或字体服务。版本、下载来源和校验值见 web/vendor/sources.json，各依赖许可证保留在同目录。

## 项目统计

Star History 展示本仓库的 Star 增长情况，点击曲线可打开交互图表。图表支持浅色和深色主题。

<a href="https://www.star-history.com/#ZhangLinqi-07/zotero-pdf2zh-body-only&amp;Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=ZhangLinqi-07/zotero-pdf2zh-body-only&amp;type=Date&amp;theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=ZhangLinqi-07/zotero-pdf2zh-body-only&amp;type=Date" />
    <img alt="Star History 星标增长曲线" src="https://api.star-history.com/svg?repos=ZhangLinqi-07/zotero-pdf2zh-body-only&amp;type=Date" width="800" />
  </picture>
</a>

顶部 README views 徽章由 [Hits](https://github.com/silentsoft/hits) 提供，从加入徽章后开始记录图像访问请求，受缓存和重复请求影响，仅作参考。维护者可在 [Insights → Traffic](https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/graphs/traffic) 查看 GitHub 统计的近期浏览、独立访客与克隆量，具体口径见 [GitHub 官方说明](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-traffic-to-a-repository)。仓库列表右侧的绿色小曲线由 GitHub 自动展示近期提交活跃度。

## 上游与许可证

上游 Zotero 插件和服务由 guaguastandup 及其贡献者开发，本项目在其 4.1.7 源码基础上加入正文翻译过滤功能。项目与上游保持独立，详细来源和修改日期见 [NOTICE.md](NOTICE.md)。

代码沿用 **GNU AGPL v3**，完整文本见 [LICENSE](LICENSE)。BabelDOC、pdf2zh_next、模型和其他依赖由各自项目维护。本仓库不分发模型权重、论文、用户环境文件、API 密钥或本地翻译缓存。
