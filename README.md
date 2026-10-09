# Clean UML Lab

从结构化事实生成简洁、可审核的 UML 类图，输出 **SVG、PNG 和可编辑 draw.io**。可作为 agent skill 或本地 CLI 使用。

本分支更新到内部阶段 **4.4**：原生文字自动扩框、保存后的文本重排、只导出一次最终 PNG，以及可选的实图文字审核。已发布的 `v0.1.0-alpha.1` 对应阶段 4.2。

![带限定符的关联](docs/images/qualified-bank.png)

## 使用

需要 Python 3.12+、Node.js 22+。在仓库目录执行：

```sh
npm ci --prefix runtime --no-audit --no-fund
python runtime/scripts/doctor.py
python prototype.py examples/qualified-bank.json --root Bank -o out/bank
```

打开 `out/bank/diagram.png`，在 draw.io 中打开 `out/bank/diagram.drawio` 编辑。输出目录必须是新目录；安装依赖后，生成可离线运行，无需 API key。中文需要系统提供中文字体。

```sh
python prototype.py examples/team.json --requirements examples/team.requirements.json -o out/team
python prototype.py examples/InviDas.json -o out/invidas
```

`run.json` 记录候选、选中结果和检查状态。`selected_valid=false` 返回退出码 2；通过自动检查的复杂图仍可能有交叉、长线或空白，需要读图确认。生成阶段先审核 SVG 候选，只栅格化最终结果一次；`--candidate-previews` 可在选择后额外生成候选 PNG。

将仓库放入 agent 的 `skills/clean-uml-lab/` 目录，并安装 runtime 依赖，即可使用 [SKILL.md](SKILL.md)。例如：

> 使用 $clean-uml-lab，根据需求画 UML 类图，保留角色、多重性和方向，输出 draw.io、SVG、PNG，并报告未通过的检查。

模型格式见 [model.md](runtime/references/model.md)。不要为布局补充或删除业务事实。

## 编辑与重排

原生标题和成员文字编辑会扩展类框，限定符保持为真实连接端。更长的文字仍可能与邻近对象相撞。保存后，用匹配的原始输出模型重排：

```sh
python reflow.py edited.drawio --model out/bank/model.json -o out/bank-reflow
```

支持类名、成员行、角色、多重性、关系标签和限定符文字的修改；新增/删除类、改连接或改 UML 类型会被拒绝。重排保留源文件，生成新模型和新图，替换手动坐标。不是与 JSON 的实时同步。

## 实图文字审核

可选工具需要 Node.js 22.12+、已安装的 Chrome/Chromium/Edge 和 Puppeteer Core：

```sh
npm install --prefix out/review-runtime puppeteer-core@25.10.0 --no-audit --no-fund
node review_svg.cjs out/bank/diagram.svg --model out/bank/model.json --engine clean --output out/bank-review --puppeteer-module ./out/review-runtime/node_modules/puppeteer-core
```

也可审核带完整同源模型的 PlantUML/Mermaid 类图 SVG，分别用 `--engine plantuml`、`--engine mermaid`。工具在独立离线浏览器中量取文字边界；无冲突为退出码 0，需要检查为 2，执行失败为 3。它检查文字边界冲突，不认证像素重叠、角色归属、业务事实或人类审美。

## 验证与边界

| 阶段 4.4 检查 | 结果与范围 |
| --- | --- |
| 复制技能包运行 | 3 个公开例子生成、1 个保存后的 Bank 文本重排，4/4 通过；都是已有开发案例 |
| 延后 PNG 导出的配对消融 | 6 个案例、12 次调用、批内返工 0；导出次数 16 → 6，最终 SVG/draw.io/PNG 和候选选择逐字节一致；不是总体延迟降低 62.5% |
| 实图审核 CLI | 从 ZIP 解压后运行 4 次，Clean/Mermaid 订单图无边界冲突，PlantUML 同事实订单图报告 17 对文字边界冲突；只代表这些固定场景 |
| 原生编辑验证 | 有原生 Graph/mxCodec API 的移动、保存、重载和命中证据；复杂编辑仍有失败案例，未认证完整桌面 GUI 操作 |

[阶段证据](docs/stage-4.4-evidence.json) · [首次公开版本历史记录](docs/release-evidence.json) · [Windows/Linux 安装与导出 CI 模板](docs/ci-smoke.yml)。当前 GitHub 授权不含 workflow 权限，模板尚未启用；远端 CI 未验收。

```sh
python verify_semantics.py out/semantic-probes
```

当前支持类、接口、抽象类、普通枚举、继承/实现/关联/聚合/组合/依赖、关联导航、显式命名空间和导入类型、有序关联端、单个命名属性限定符。尚不覆盖完整 UML：包框、多属性/类型限定符、枚举操作、时序图和活动图等未实现。

复杂布局正在继续研究。现有证据不支持“全面领先所有竞品”；几何指标和工程检查不等于人类偏好、理解效率或独立绘图 skill 的盲测结果。

## 许可与例图

代码和自建例子为 [MIT](LICENSE)。InviDas 原始模型、投影及生成图源于 CC BY 4.0 数据，作者和修改说明见 [ATTRIBUTION.md](examples/ATTRIBUTION.md)，该署名许可继续适用。许可未明确的研究输入没有随仓库发布。

![InviDas：32 个类与枚举](docs/images/InviDas.png)

[可编辑工业例图](docs/images/InviDas.drawio) · [SVG](docs/images/InviDas.svg) · [中文小例子](docs/images/team.png)
