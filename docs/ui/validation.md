# Kinbo UI 第一阶段验证

## 0.4.4 正式发行构建补充

Kinbo 0.4.4 / 插件 4.1.7.16 在第一阶段 UI 提交基础上增加正式版本信息、Kinbo 插件名称与图标，并重写产品 README。发布前再次运行 172 项 Python 测试：161 项通过、11 项因缺少原生翻译引擎条件跳过；五组 JavaScript 检查、后台空闲等待/真实重启/配置与笔记保留集成测试均通过。

使用正式候选 XPI 在隔离 Zotero 10.0.7 资料库验证安装，确认显示名 Kinbo、版本 4.1.7.16、浅深色、336px 侧栏、阅读启动/停止菜单、选文、模型配置、历史、原文引用、高亮、窗口切换及停用卸载清理。模型接口均为模拟，未使用私人论文或调用收费模型。

候选 XPI SHA-256：`c87491ab99bb9d438c1e1e70006d905113dba938c16a9ab44d352b22d65cb984`。正式分发文件及更新清单由标签发布工作流下载复核后切换；以 Release 的 SHA256SUMS.txt 为公开下载校验依据。

下文保留开发提交 `83819c3` 的历史记录，其中「版本不变、仅推送源码」描述的是正式发布前的 UI 阶段，发行信息以本节和 [发布说明](../release-notes.md) 为准。

日期：2026-11-03。范围为插件内论文对话、右键菜单收敛、资源打包和 Reader 生命周期。所有论文及回答均为合成测试内容，未调用真实模型或付费 API，未使用日常 Zotero 资料库、配置或后台。

## 自动测试

工作区基线与改造后均通过 `python -m unittest discover -s tests -v`（在已有、具备 Flask/PyMuPDF 的服务 Python 环境中运行）：174 项运行，163 项通过，11 项跳过。跳过项需要独立原生翻译引擎，不计为通过。系统默认 Python 缺少 Flask/PyMuPDF 的首次运行有 10 项导入/依赖错误，随后切换解释器验证，未更改系统环境。

最终提交前另从 Git 暂存区导出干净源码，排除原有 Codex 改动：172 项运行，161 项通过、11 项跳过；下列五组 JavaScript 检查均再次通过。由该副本构建 XPI 并完成原生 Zotero 验证，避免将无关后台改动带入验证包。

以下 JavaScript 检查均通过：

```text
node tests/test_paper_chat_ui.js
node tests/test_note_format.js
node tests/test_reading_bridge.js
node tests/test_reading_backend_ui.js
node tests/test_backend_update.js
```

论文对话新增回归覆盖：完整末页输入、旧会话恢复、API/Codex 参数、输入法组合不发送、清空需确认、失败恢复保留回答且不生成、主题变更、关闭后返回的配置/登录不复活轮询、Reader 等待定时器取消、dead DOM 按钮清理及所有已注册监听解除。包测试覆盖新模块、样式、六个图标、ID/版本/更新地址/兼容范围与可重复构建。

## 浏览器与设计审查

独立预览直接复用 `paper_chat_view.js` 和 `paper_chat.css`。Chrome 共验证 64 组组合：1440×900、768×1024、390×844、1024×700（264px 侧栏）× 浅/深色 × 正常、选文、引用、联网、模型、生成、失败、空状态。控件无横向溢出；正文、辅助文字、引用、错误和主按钮语义颜色对均达到 4.5:1；键盘发送、开关与重新打开可用。

Taste app inspector 为 0 FAIL；两条 WARN 经独立审查确认：合成 PDF 纸张的留白属于版式，390px 的 12px 内距用于桌面窄侧栏 QA。Hallmark Custom 采用 app scope，未套用营销构图；最终静态检查为 0 FAIL / 0 REFLEX / 0 WARN。Impeccable detector 运行一次，输出空数组。

独立 finish reviewer 查看 12 张覆盖主题/状态/宽度的有效截图，指出失败恢复预览与正式路径不一致、方向契约工具记录不准确两项；修复后 verdict pass 对两项均判定 resolved / ship。该复核结论限于所列修复，不代表完整产品迁移验收。

## 真实 Zotero

在 Zotero 10.0.7 中通过常规 XPI 安装，用新的隔离 profile、独立资料库、两页合成 PDF、模拟 HTTP 接口验证：

- 全部页面文本、原句唯一匹配及 41 个字符矩形；
- 侧栏 336px、浅深色的实际 computed style、左右切换、选文展示与发送、停止生成、模型列表；
- 物理页码引用、原生点击、高亮显示及关闭清理；
- 已有历史与重新打开、主窗口/独立 Reader 窗口切换；
- 单一菜单启动模拟深度阅读、切换到停止并取消、管理入口迁到 Tools 和 SVG 资源；
- 插件停用后侧栏、工具栏和 Tools 菜单移除，卸载完成。

迭代过程保留了失败证据：一次截图路径混用斜杠失败；两次隔离 profile 的初始文库加载与创建合成条目竞争，卡在 Reader.open；等待初始 item 数据完成后已解决。窗口测试还找出了 Gecko dead wrapper 中断插件清理的问题，已在 Reader 适配层处理并新增回归。

真实输入控件的背景分别核对为 `rgb(255,255,255)` 与 `rgb(38,42,47)`，深色图标为 `rgb(229,233,237)`。Zotero chrome 对表单的覆盖通过 `no-native` 外观退出属性处理。隐藏测试窗口不会稳定推进合成器过渡，最初的图标颜色断言因此失败；原生截图测试将反馈时长设为 0ms 后验证稳定状态，不修改生产动画或用户偏好。

本地验证包 SHA-256：`66fefed0255e02ebf67525b42ea1b4e3f675c1d05c8b9bb22f31e12236e9b57f`。ID、版本与自动更新地址沿用当前值，本地包仅供审阅，不作为正式发布物。

集成入口：

```text
python tests/integration_chat_reader.py --zotero <Zotero可执行文件> --xpi <本地构建XPI> --output-dir <新的隔离目录>
```

测试记录与截图保留在本地忽略目录，不随提交发布。

## 工程边界

后台 Web 页、Python 源码、API 协议、完整输入方式、生产数据、插件 ID、发布版本常量、updates.json 均未在本次 UI 变更中修改。仓库开始时已有的 Codex 后端及其测试/校验清单改动不纳入本次提交。推送仅为源码，不发布版本或触发自动更新，也未向用户日常 Zotero 安装验证包。

剩余上游 UI 与身份迁移任务见 [架构审计](../kinbo-ui-architecture.md)。本轮没有测试真实模型生成质量、收费 API 的联网检索、原生翻译引擎或其他 Zotero/操作系统版本；这些不由模拟 UI 验证代替。
