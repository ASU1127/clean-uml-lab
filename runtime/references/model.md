# 模型：语义扩展开发版

根对象为 `nodes`、`relations`。可选 `package` 是命名空间路径列表，例如 `["bank.core"]`，作为未声明包的节点的默认值。节点上的 `package` 为绝对覆盖，例如 `["bank.customers"]`；列表中多个名称表示嵌套路径。图中使用 `bank::core::Bank` 形式保留包归属，不增加包外框。原始声明和有效路径保存在 `namespace-audit.json`。不猜测源语言默认包或代码生成时的命名空间转换。

可选 `imports` 是显式限定类型名列表，例如 `["java.time.ZonedDateTime"]`。只解析成员属性、参数和返回类型，展开为完整限定名；原始输入与绑定记录保留。支持限定名称、嵌套泛型和数组；不支持通配导入、static 导入或通配泛型。冲突绑定明确拒绝。没有 `imports` 的原有文本保持不变。1–40 个节点、最多 100 条关系为此版规模边界，不是 UML 规范限制。

每个节点：`id` 唯一 ASCII 标识（字母/下划线开头）；`name` 原语言显示名；`kind` 为 `class`、`abstract`、`interface` 或 `enum`；`members` 为完整成员文本列表，没有则 `[]`。枚举仅支持普通字面量名称，绘制 `«enumeration»`。成员如 `-编号 : String`、`+find(id : String) : Book`。可选 `visibility` 为 `public` 或 `private`，标题保留 `+` / `-` 符号。不同命名空间可有同名类，完全相同限定名拒绝。任意 Creole 标记不支持。文本上限 320 字符；不支持时报告而不截断。

关系：`kind`、`source`、`target` 必需，引用节点 id。

| kind | source | target |
|---|---|---|
| generalization | 子类/子接口 | 父类/父接口 |
| realization | 实现类 | 接口 |
| association | 关联一端 | 关联另一端 |
| dependency | 依赖者 | 被依赖者 |
| composition / aggregation | 整体 | 部分 |

可选 `label` 为关系名。关联、组合、聚合可设置 `source_multiplicity`、`target_multiplicity` 及 `source_role`、`target_role`。
角色/多重性跟随命名端点，不跟随屏幕左右。未知就省略字段，不能填 null；支持 `0..1`、`1`、`*`、`0..*`、`1..*` 和数值区间。自关联可用两个角色区别。
`navigability` 为关联的可选可导航性：`--`、`->`、`<-`、`<->`，按模型 source/target 端解释，屏幕位置变化不会改变语义。组合/聚合的整体端同时画可导航箭头与菱形尚未实现，明确拒绝。允许同端点同种关系具有不同角色/名称等事实；完全相同的重复声明仍拒绝，以免误合并。枚举操作、继承和实现尚不支持。

同一类到自身的组合在类级别并非一律非法；实例层面的组合环不由本编译器验证。

`source_ordered` / `target_ordered` 是显式布尔值：`true` 显示 `{ordered}`，`false` 显示 `{unordered}`，未提供则不添加默认值。只用于关联、组合或聚合端。

`source_qualifier` / `target_qualifier` 的格式为 `{"kind":"attribute","name":"accountNo"}`。它表示该命名端拥有的限定符属性，矩形附着在这个端对应的类框；筛选结果的多重性仍放在对端。类型未知时只显示名称。当前只支持一个属性名，不支持按类型或多属性限定。限定符是关联的组成部分，在 draw.io 中使用附着类框的矩形和关联所有者元数据，连线连接到矩形的真实端点。限定符通过图形编译器绘制，旧 PlantUML 文本序列化明确拒绝此功能，不静默省略。

表示依据：[OMG UML 2.5.1](https://www.omg.org/spec/UML/2.5.1/PDF)，命名空间 7.4、顺序 7.5、限定关联 11.5（图 11.37）。这不是全 UML 规范或源语言编译器认证。

```json
{
  "nodes": [
    {"id":"staff","name":"Employee","kind":"class","members":["-name : String"]}
  ],
  "relations": [
    {"kind":"association","source":"staff","target":"staff","source_role":"manager","source_multiplicity":"0..1","target_role":"reports","target_multiplicity":"0..*"}
  ]
}
```
这个例子表示一个员工最多有一个经理，一个经理可有多个下属；是否允许自己管理自己需要另行约束，不能由自关联图形自动判定。

## 可选需求断言
先从明确需求写断言，然后生成模型。`required_nodes` / `required_relations` / `forbidden_nodes` / `forbidden_relations` 是对象列表，按包含字段匹配，字段必须使用上述格式。
例如 `{"required_nodes":[{"name":"Employee"}],"forbidden_relations":[{"kind":"composition"}]}`。
断言只检查调用方列出的内容，不会理解原始自然语言，也不能当成独立人工真值。
