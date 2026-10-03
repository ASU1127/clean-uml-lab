# Clean UML Lab

从结构化事实生成简洁、可审核的 UML 类图，输出 **SVG、PNG 和可编辑 draw.io**。面向 AI 编码助手的 skill，也可以作为本地 CLI 使用。

**首个公开版本：`v0.1.0-alpha.1`（内部阶段 4.2）。** 已具备实用的类图生成流程；复杂布局和完整 UML 覆盖仍在迭代。

![包含限定符和斜线的类图](docs/images/qualified-bank.png)

## 能做什么

- 保留类、接口、抽象类、枚举、成员、关联方向、角色名和多重性。
- 支持继承、实现、关联、聚合、组合和依赖；支持显式命名空间、导入类型、有序关联端与单属性限定符。
- 比较有限数量的布局候选，允许自然的斜线，检查标签、箭头、节点冲突和继承层次。
- 输出候选记录、需求断言检查与 draw.io 语义元数据。所有候选都未通过自动检查时，CLI 返回退出码 `2`。

生成流程：`需求 → JSON 事实模型 → 布局候选 → 自动检查 → SVG / PNG / draw.io`。LLM 负责理解需求和建立模型，本地程序负责绘图；生成阶段不调用模型 API。

## 开始使用

需要 **Python 3.12+、Node.js 22+**。下载或克隆本仓库后，在仓库目录执行：

```sh
npm install --prefix runtime --no-audit --no-fund
python runtime/scripts/doctor.py
python prototype.py examples/qualified-bank.json --root Bank -o out/bank
```

打开 `out/bank/diagram.png` 查看图片，在 draw.io 中打开 `out/bank/diagram.drawio` 继续编辑。`out/bank/run.json` 包含选中候选、自动检查状态、几何指标和运行耗时；`index.html` 汇集本次候选。

输出目录必须是新目录。`--root ID` 指定主对象，主次明确时建议使用。安装依赖后，生成可离线运行，无需 API key。中文图需要系统提供中文字体；doctor 的成功不代表中文字体覆盖已验收。

带独立需求断言的例子：

```sh
python prototype.py examples/team.json --requirements examples/team.requirements.json -o out/team
```

工业模型：

```sh
python prototype.py examples/InviDas.json -o out/invidas
```

CLI 接收 JSON；附带的 `InviDas.cd` 用于来源对照，不是可直接解析的输入。事实模型见 [model.md](runtime/references/model.md)，不要为改善布局擅自补充或删除关系。

## 作为 skill

将本仓库作为 `clean-uml-lab` 文件夹放进支持 `SKILL.md` 的 agent 的 skills 目录，并安装 `runtime` 依赖。在 Codex 中，通常使用 `~/.codex/skills/clean-uml-lab/`。

调用示例：

> 使用 `$clean-uml-lab`，根据下面的需求画 UML 类图。保留角色和多重性，输出可编辑 draw.io、SVG、PNG，并报告未通过的检查。

入口：[SKILL.md](SKILL.md)。当前 skill 需要能够运行 Python、Node.js 和本地文件的环境。

## 当前验证结果

这是小规模工程验证，自动检查通过不等于人类审美验收。

| 检查 | 结果与边界 |
| --- | --- |
| 4 个已有开发模型 | 显式声明映射 4/4；首轮布局 3/4 通过，一次选择策略修复后 4/4。不是新留出测试集 |
| 打包后 CLI | Bank、University、SocNet 三个模型通过；10 次独立 XML 语义导出检查通过 |
| draw.io 原生模型 API | 2 个模型、28 项移动/编辑/保存/重载检查通过；未认证完整桌面 GUI 交互 |
| 工业例子 InviDas | 32 个类/枚举、93 个成员、27 条关系；自动统计 0 个严格线段交叉、5 次转折 |

Windows 上的单次打包测试：2 个类约 **1.4 秒**，9 个类约 **3.2 秒**，10 个类约 **6.5 秒**；32 个类的开发运行约 **15 秒**。这些耗时包括候选布局、导出和检查，不能与只导出一张 SVG 的渲染器直接比较。

保留的消融结果：

| 单项变化 | 固定条件 | 结果 |
| --- | --- | --- |
| 基线无效时优先选择通过检查的候选 | 相同候选与审核结果，回放不增加布局调用 | 通过数 3/4 → 4/4；University 面积增加约 15%，转折 6 → 2 |
| 标签避让限定符矩形 | 相同事实、节点和连线几何 | 自建 Bank 标签冲突 1 → 0；SocNet 0 → 0，不计作提升 |

已对相同 InviDas 事实运行过 Mermaid、PlantUML 原生默认渲染，另有早期 drawio-skill 顺序试验。当前证据不支持“全面领先所有竞品”；未进行盲测或独立用户理解实验。研究中许可未明确的输入没有随仓库发布，因此并非所有历史试验都能从本仓库重跑。

机器可读汇总：[release-evidence.json](docs/release-evidence.json)。本地可运行的语义与限定符检查：

```sh
python verify_semantics.py out/semantic-probes
```

[GitHub Actions 模板](docs/ci-smoke.yml) 包含 Windows/Linux 的语义、依赖和导出检查。当前发行版已在 Windows 本地验证；模板尚未启用，远端 CI 与 Linux 运行未验收。

## 已知边界与下一步

- 当前专注 UML 类图子集，尚不支持时序图、活动图、包框、多属性或类型限定符等完整 UML 表达。
- 复杂图可能保留交叉、长线和较大空白；`selected_valid=true` 仍需要读图确认。
- draw.io 编辑不会同步回原 JSON；改长文字可能超出固定框，需要修改 JSON 后重新生成。
- 不校验 MontiCore 原生语言的全部隐式规则，也不会自动证明业务事实正确。

下一阶段优先改善复杂图布局，再加入新模型留出集、相同预算的竞品对照和独立用户理解测试。提交问题时可附脱敏模型、`run.json` 与截图。

## 许可与例图

代码及自建例子为 [MIT](LICENSE)。InviDas 原始模型、投影及对应生成图源于 CC BY 4.0 数据，作者和修改说明见 [ATTRIBUTION.md](examples/ATTRIBUTION.md)；该数据的署名许可继续适用。

![InviDas 工业模型：32 个类和枚举](docs/images/InviDas.png)

[可编辑工业例图](docs/images/InviDas.drawio) · [工业例图 SVG](docs/images/InviDas.svg) · [自建中文例图](docs/images/team.png)
