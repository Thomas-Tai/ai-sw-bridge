# ai-sw-bridge

> **Language**: [English](../../README.md) · 简体中文 (简体中文)

一个半自动化的桥接工具，让 AI 助手（Claude、ChatGPT、Codex 等）通过 COM API 驱动 SOLIDWORKS。

## 它能做什么

目前，ai-sw-bridge 沿着从观察到 AI 驱动创建的连续光谱，提供**四项能力**：

| 能力 | CLI 命令 | 提供的功能 |
|---|---|---|
| **检查** | `ai-sw-observe` | 以 JSON 格式读取特征、方程式、配合、截图。随时可安全运行。 |
| **变量修改** | `ai-sw-mutate` | 对 `*_locals.txt` 变量进行 Propose–Approve–Execute 修改。提交前进行 dry-run + rollback。 |
| **录制宏参数化**（Path C） | `ai-sw-codegen` | 在 SW UI 中录制一次，针对 `*_locals.txt` 进行参数化，回放以重新生成。 |
| **声明式零件合成**（v0.2，开发中） | `ai-sw-build` | 接收描述特征和参数绑定的 JSON spec，通过 direct-COM 驱动 SW 生成零件。**AI 原生创作路径。** |

长期目标是第四项能力：AI 助手读取设计指南，输出 JSON 零件 spec，驱动 SOLIDWORKS 构建它，并验证结果——全部通过可 diff、版本控制的产物完成。阶段 0 和 1 已落地；MMP（电机安装板）是一个部分端到端演示。完整计划见 [docs/ai_driven_architecture_review.md](docs/ai_driven_architecture_review.md)。

围绕 **Propose–Approve–Execute** 纪律设计：每次修改都先以 dry-run + rollback 运行，展示差异，只有在明确批准后才提交。AI 永远不会拿到你 CAD 模型的"随便操作"按钮。

## 当前状态（2026-05-17）

**v0.1 能力 — 生产验证通过** 在 SOLIDWORKS 2024 SP1 上：
- `ai-sw-probe`、`ai-sw-observe`、`ai-sw-mutate` 端到端正常工作
- Path C 参数化已在单次拉伸圆柱体上验证

**v0.2 能力 — 阶段 1 GREEN：**
- 阶段 0 spike：**GREEN** — direct-COM late-binding 对 v0.2 架构可行
- 阶段 1（JSON-spec 构建器）：**GREEN**
  - 圆柱体示例端到端构建，支持参数绑定
  - **电机安装板（MMP）端到端构建 10/10 特征**，含 7 个参数绑定（50×50 板，带同心 Ø12 联轴器孔 + Ø20.5 法兰凹槽 + ±15mm 处的电机/框架孔对）。几何验证居中。
- **CHM 验证的 API 参考**（[docs/api_reference.md](docs/api_reference.md)）— 从官方 `sldworksapi.chm` 提取的 23 个在用 SW 方法 + 5 个枚举，运行时进行参数数量断言

## 为什么这很重要

**构建 AI 驱动的 SOLIDWORKS 自动化是真正的 R&D。** SW 社区花了十年构建插件框架（angelsix、xCAD、codestack）和仅修改的封装器（pyswx、pySldWrap），但没有人交付过声明式零件构建器。ai-sw-bridge 的 v0.2 工作正是填补这一空白——参见 [docs/ai_driven_architecture_review.md](docs/ai_driven_architecture_review.md) 中的领域调研。

现在可行的原因：

- **AI 助手擅长 JSON。** spec 是纯数据，不是 VBA 散文。AI 编写 spec，桥接工具运行它。
- **通过 pywin32 late-binding 的 direct-COM 可行**，适用于我们测试过的 SW 版本上的大多数 SW API。"cut 不可用"这个结论是错误的（见 commit `c560e97`）——只要传入 `FeatureCut4` 期望的全部 27 个参数（而非旧文档暗示的 24 个），它就能正常工作。
- **权威的 API 签名。** 当 SW 调用返回 `PARAMNOTOPTIONAL` 时，第一件事就是检查 `sldworksapi.chm` 中的参数数量。我们已将此查找过程编码化；见 [tools/chm_extract.py](tools/chm_extract.py)。

## 限制（采用前请阅读）

**平台与 API**

- **仅限 Windows。** SOLIDWORKS 仅支持 Windows，`pywin32` 也仅支持 Windows。
- **仅支持 pywin32 late-binding。** `EnsureDispatch`/makepy 在大多数安装上对 `SldWorks.Application` 不起作用。后果：带有 `OUT` 参数或 COM 接口参数的 API 方法（例如 `SelectByID2` 的 `Callout`、`AddSpecificDimension` 的 `Error`）不可达。每个新 API 表面都需要沙盒确认。见 [docs/known_gotchas.md](docs/known_gotchas.md)。
- **SW 状态不可见。** SW 状态机（活跃 sketch、当前选择、编辑模式）存在于 SW 的 UI 内存中；API 无法可靠地查询它。每个操作都必须显式设置状态。
- **`AddDimension2` 会打开 Modify Dimension 弹窗**，在参数化模式下需要手动点击。`swInputDimValOnCreate`（toggle 8）和 `swSketchEnableOnScreenNumericInput` 类（toggle 78）偏好设置在 SW 2024 SP1 上通过 pywin32 经验证无法抑制。记录于 [spikes/phase0/MMP_DEBUG_SESSION.md](spikes/phase0/MMP_DEBUG_SESSION.md)。**已提供解决方案：`ai-sw-build --no-dim`** 在 Python 中预先将 `{rhs}` 引用解析为 `locals.txt` 中的字面值，并以目标尺寸构建几何，跳过所有 `AddDimension2` 调用。权衡：生成的 SLDPRT 没有到 `locals.txt` 的方程式链接（编辑 locals 需要重新运行 `ai-sw-build`）。MMP `--no-dim` 模式约 3 秒完成，0 次手动点击；参数化模式约 60 秒 + ~16 次点击。

**性能与 AI 迭代**

- **COM 每次调用约 5-50ms。** 一个 30 特征的零件需要约 200 次调用 = 30-120 秒端到端。AI 迭代必须是"先规划后执行"，而不是逐次调用。

**范围（v0.2 当前）**

- **没有流畅的零件构建器 API。** 没有 `part.box().hole()` 链式调用。v0.2 是 JSON-spec → direct-COM。AI 生成 spec JSON，不是自由散文。
- **有限的面/边选择。** SW 通过 3D 坐标选择面，而非"特征 X 的外侧"。构建器从特征几何计算坐标，并在早期特征已在中心处切除材料时尝试小偏移作为回退。在同心孔等边缘情况下较为脆弱。
- **没有圆角、扫掠、放样。** 需要人工判断（哪些边）或不易映射到声明式 spec 的路径几何。已推迟。
- **没有装配体、没有配合、没有工程图。** 每个都是独立的问题。当前桥接工具仅处理零件级工作流。
- **没有"用英语描述零件然后获得几何体"。** spec 语言是精确的。AI 生成 spec JSON。
- **不会取代 CAD 工程师。** 这是一个让设计师更高效、更可复现的工具。

## 快速入门

### 前置条件

- **Windows**（SOLIDWORKS 仅支持 Windows，`pywin32` 也仅支持 Windows）
- **SOLIDWORKS** 已安装并运行（在 2024 SP1 上测试；应在 2021 SP5+ 上工作）
- **Python 3.10+**（在 3.14 上测试）

### 安装

```powershell
git clone https://github.com/Thomas-Tai/ai-sw-bridge.git
cd ai-sw-bridge

python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

安装后，**五**个 CLI 命令在你的 PATH 上：

| 命令 | 用途 |
|---|---|
| `ai-sw-probe` | COM 连接健康检查 |
| `ai-sw-observe` | 只读检查（特征、方程式、配合、截图） |
| `ai-sw-mutate` | 对 `*_locals.txt` 变量进行 Propose–Approve–Execute 修改 |
| `ai-sw-codegen` | Path C：将录制的 `.swp` 宏参数化 |
| `ai-sw-build` | **v0.2**：通过 direct-COM 从 JSON spec 构建零件 |

### 冒烟测试

打开 SOLIDWORKS，然后运行：

```powershell
ai-sw-probe
```

你应该看到：
```json
{
  "ok": true,
  "sw_revision": "32.1.0",
  "active_doc": null,
  "error": null
}
```

## 五分钟教程

### 1. 检查模型（安全、只读）

```powershell
ai-sw-observe active_doc
ai-sw-observe feature_errors
ai-sw-observe equations
ai-sw-observe screenshot --width=1280 --height=720
ai-sw-observe mate_errors                              # 仅限装配体
ai-sw-observe measure                                  # 使用当前 SW UI 选择
```

每个命令向 stdout 打印一个 JSON 对象。失败时退出码非零。

### 2. 修改参数变量（Propose–Approve–Execute）

你的活跃 SOLIDWORKS 零件必须有一个链接的 `*_locals.txt` 方程式文件：

```powershell
ai-sw-mutate propose --var=PART_DIAMETER --new_value=30.0
# -> { "proposal_id": "abc123def456", ... }

ai-sw-mutate dry_run --proposal_id=abc123def456     # 应用、重建、捕获、回滚
ai-sw-mutate commit  --proposal_id=abc123def456     # 仅在 dry_run_ok 后允许
ai-sw-mutate undo_last_commit
```

提案以 JSON 形式持久化在 `./proposals/` 中，以便 AI 助手可以跨会话恢复。

### 3. 从 JSON spec 构建零件（v0.2，direct-COM）

**默认使用 `--no-dim` 模式。** 它在几秒内完成，零手动点击。仅当你特别需要到 `locals.txt` 的实时方程式链接时才使用参数化模式（见下方"两种构建模式"）。

打开 SOLIDWORKS（不需要打开零件——构建器会创建一个新的），然后运行：

```powershell
# 最小的端到端示例：20×20×10 盒子，一个边有 2mm 圆角
ai-sw-build examples/filleted_box/spec.json --no-dim
```

预期输出（约 3 秒）：

```json
{
  "ok": true,
  "features_built": ["SK_Box", "Extrude_Box", "Fillet_TopRightEdge"],
  "bindings_added": [],
  "save_as": null,
  "no_dim": true
}
```

另外三个示例，按复杂度递增：

```powershell
ai-sw-build examples/minimal_cylinder_v2/spec.json   --no-dim    # 2 个特征
ai-sw-build examples/motor_mount_plate/spec.json     --no-dim    # 10 个特征
ai-sw-build examples/tension_bracket/spec.json       --no-dim    # 8 个特征，堆叠拉伸
```

spec 是一个声明特征的按构建顺序排列的小型 JSON 文件。长度为字面 mm 值（`20.0`）或绑定到 `*_locals.txt` 文件中变量的表达式（`{"rhs": "\"PART_DIAMETER\""}`）：

```json
{
  "schema_version": 1,
  "name": "MyCylinder",
  "locals": "C:\\path\\to\\globals_locals.txt",
  "features": [
    {"type": "sketch_circle_on_plane", "name": "SK_Body", "plane": "Front",
     "diameter": {"rhs": "\"PART_DIAMETER\""}},
    {"type": "boss_extrude_blind", "name": "Extrude_Body", "sketch": "SK_Body",
     "depth": {"rhs": "\"PART_LENGTH\""}}
  ]
}
```

构建器验证 spec（schema + 拓扑引用 + locals 文件变量），通过 `NewDocument` 创建新零件，按顺序遍历特征，发出 direct-COM 调用。输出为包含 `features_built` 和（在参数化模式下）`bindings_added` 的 JSON。

#### 两种构建模式

| 模式 | 标志 | 何时使用 | 权衡 |
|---|---|---|---|
| `--no-dim`（推荐） | `--no-dim` | 首次测试。spec 为唯一真实来源的任何场景。桥接工具在每次编辑后重新运行的 AI 驱动流程。 | 生成的 SLDPRT 没有到 `locals.txt` 的方程式链接。之后编辑 locals 需要重新运行 `ai-sw-build`。 |
| 参数化（默认） | *（无标志）* | 当人类之后会手动编辑 SLDPRT 并需要到 `locals.txt` 的实时链接时。 | 每个 `AddDimension2` 调用都会打开一个阻塞的"Modify Dimension"弹窗，需要手动鼠标点击。一个 MMP 大小的零件约 16 次点击。在 SW 2024 SP1 上无法抑制；见 [docs/known_limitations.md](docs/known_limitations.md) 中一系列失败的抑制尝试。 |

在 `--no-dim` 模式下，每个 `{"rhs": "..."}` 引用都会在 Python 中预先解析为 `spec['locals']` 的字面 mm 值，在任何 SOLIDWORKS 调用之前替换。几何以正确尺寸输出；SLDPRT 只是没有方程式。

#### 编写你自己的 spec 之前

**先阅读 [docs/known_limitations.md](docs/known_limitations.md)。** 三个尖锐边缘会绊住编写第一个非示例零件的人：(1) 面 sketch 原点是零件原点到面的投影，*不是*面的几何中心；(2) 当前只有拉伸体的 +/-z 面可以承载子 sketch；(3) 参数化模式的弹窗代价。这三者都有文档记录的解决方案，从 schema 的首次阅读中都看不出来。

### 4. 手动录制零件的参数化回放（Path C）

对于 v0.2 spec 语言尚未覆盖的形状（圆角、扫掠、复杂轮廓），Path C 让你在 SW UI 中录制一次然后参数化回放：

```powershell
# 在 SW 中录制零件（工具 → 宏 → 录制）。保存为 recorded.swp。
# 编写一个小型 spec，将录制的尺寸映射到你的变量。
ai-sw-codegen parameterize examples/minimal_cylinder/recorded.swp examples/minimal_cylinder/spec.json
# 将生成的 .bas 粘贴到 VBE 中，按 F5。
```

见 [examples/minimal_cylinder/README.md](examples/minimal_cylinder/README.md)。

## API 参考（CHM 验证）

桥接工具维护着它调用的每个 SW API 的权威参考，从 `sldworksapi.chm` 提取：

- [docs/api_reference.md](docs/api_reference.md) — 人类可读：签名、参数文档、枚举值、可用性
- [docs/api_reference.json](docs/api_reference.json) — 机器可读

### 支持的 SW API 表面

7 个接口上的 24 个方法和 5 个枚举。每次调用的确切参数数量在运行时由 [src/ai_sw_bridge/sw_types.py](src/ai_sw_bridge/sw_types.py) 断言——CHM 与我们调用之间的偏差会快速失败，错误信息中包含预期签名。完整的逐方法参数列表见 [docs/api_reference.md](docs/api_reference.md)。

**`ISldWorks`**（应用级）

| 方法 | 参数数 | 用途 |
|---|---|---|
| `NewDocument` | 4 | 从模板创建新的零件/装配体/工程图 |
| `GetUserPreferenceStringValue` | 1 | 读取字符串偏好（如默认模板路径） |
| `GetUserPreferenceToggle` | 1 | 读取布尔偏好 |
| `SetUserPreferenceToggle` | 2 | 写入布尔偏好 |

**`IModelDoc2`**（文档级）

| 方法 | 参数数 | 用途 |
|---|---|---|
| `SelectByID` | 5 | 按名称 + 3D 坐标选择实体（旧版 5 参数形式；`SelectByID2` 的 `Callout` 参数通过 late-binding 不可达） |
| `ClearSelection2` | 1 | 清除当前选择 |
| `AddDimension2` | 3 | 在引线位置添加显示尺寸 |
| `FeatureByPositionReverse` | 1 | 获取倒数第 N 个特征（用于抓取刚构建的特征进行重命名） |
| `EditRebuild3` | 0 | 仅重建活跃配置中的过期特征（作为属性自动调用） |
| `EditUndo2` | 1 | 撤销 N 个操作 |
| `Parameter` | 1 | 获取命名尺寸参数（`"D1@Sketch1"`）用于检查 |
| `GetFeatureCount` | 0 | 计算文档中的特征数（作为属性自动调用） |
| `SaveBMP` | 3 | 将当前视图保存为 BMP |

**`IModelDocExtension`**

| 方法 | 参数数 | 用途 |
|---|---|---|
| `SelectByID2` | 9 | 文档记录的 9 参数选择；`Callout` 接口参数通过 pywin32 late-binding 编组失败，因此我们改用旧版 `SelectByID` |

**`IFeatureManager`**

| 方法 | 参数数 | 用途 |
|---|---|---|
| `FeatureExtrusion2` | 23 | Boss 拉伸（用于 v0.2 中所有 boss/拉伸特征） |
| `FeatureExtrusion3` | 23 | 较新的拉伸变体（相同参数形状；当前未使用） |
| `FeatureCut4` | 27 | Cut 拉伸（用于 v0.2 中所有 cut 特征）。**CHM 说 27 个参数** — 缺少的 `AutoSelectComponents`、`PropagateFeatureToParts`、`OptimizeGeometry` 导致了我们之前的 `PARAMNOTOPTIONAL` 失败 |
| `CreateDefinition` | 1 | 创建按特征类型的数据对象（用于 SW 2020+ 规范圆角路径；接受 `swFeatureNameID_e` 整数，如 `swFmFillet=1`）。替代了圆角/倒角已弃用的单次调用形式 |
| `CreateFeature` | 1 | 消费已填充的特征数据对象并创建特征。Late-binding 对 CDispatch 的直通传递已验证可行（Spike P） |

**`ISketchManager`**

| 方法 | 参数数 | 用途 |
|---|---|---|
| `InsertSketch` | 1 | 在活跃上下文中打开/关闭 sketch |
| `CreateCornerRectangle` | 6 | 通过两个对角点创建矩形（在 v0.2 中未使用 — 无约束，导致尺寸绑定时不对称缩放） |
| `CreateCenterRectangle` | 6 | 通过中心 + 角点创建矩形。通过中心对角线锚定，使尺寸缩放保持居中 |
| `CreateCircle` | 6 | 通过中心点 + 圆周点创建圆 |

**`IEquationMgr`**

| 方法 | 参数数 | 用途 |
|---|---|---|
| `Add2` | 3 | 添加方程式行（如 `"D1@SK_Plate" = "S1B_W"`）。必须先完成 4 次调用链接序列（`FilePath` + `LinkToFile=True` + `AutomaticRebuild=True` + `UpdateValuesFromExternalEquationFile`） |

**`IFeature`**

| 方法 | 参数数 | 用途 |
|---|---|---|
| `GetTypeName` | 0 | 区分"Boss"与"Cut"特征（作为属性自动调用） |
| `GetNextFeature` | 0 | 遍历特征树（作为属性自动调用） |

**枚举**（来自 `swconst.chm`，在 [`sw_types.py`](src/ai_sw_bridge/sw_types.py) 中作为常量暴露）

| 枚举 | 值数 | 备注 |
|---|---|---|
| `swEndConditions_e` | 11 | `swEndCondBlind=0`、`swEndCondThroughAll=1`（不是 4 — 4 是已弃用的 `swEndCondUpToSurface`）、`swEndCondMidPlane=6` 等 |
| `swStartConditions_e` | 4 | `swStartSketchPlane=0`（所有 v0.2 拉伸的默认值） |
| `swDocumentTypes_e` | 8 | Part=1, Assembly=2, Drawing=3 |
| `swDimensionType_e` | 17 | 用于 `AddSpecificDimension`（由于 OUT 参数编组问题当前不可达） |
| `swSelectType_e` | — | 字符串形式，用作 `SelectByID` 的第 2 个参数（"PLANE"、"FACE"、"SKETCH"、"SKETCHSEGMENT"） |

**尚未接入桥接工具**（但在 CHM 中可用，v0.3+ 候选）：
`FeatureRevolve`、`FeatureChamferType`、`InsertCutSwept5`、`InsertProtrusionSwept`、`FeatureCutThin2`、`FeatureBossThin2`、`SimpleHole3`、`InsertMirrorFeature`、`InsertLinearPatternFeature`。将它们添加到 [`tools/_api_extract_input.json`](tools/_api_extract_input.json) 并重新生成即可通过 `sw_types.py` 暴露。

定半径圆角已接入（通过 `CreateDefinition` + `ISimpleFilletFeatureData2` + `CreateFeature` 3 次调用管线添加，而非已弃用的 `FeatureFillet3`）。用法见 [`examples/filleted_box/`](examples/filleted_box/)。变半径/非对称/ setback 圆角尚未接入（暂无直接用例）。

生成方式：

```powershell
# 1. 反编译 CHM（一次性设置）
hh.exe -decompile spikes/phase0/_chm_decompiled "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\sldworksapi.chm"

# 2. 提取 tools/_api_extract_input.json 中声明的方法和枚举
python tools/chm_extract.py batch tools/_api_extract_input.json docs/api_reference.json

# 3. 重新生成人类可读和 Python 存根形式
python tools/gen_api_markdown.py docs/api_reference.json docs/api_reference.md
python tools/gen_sw_types.py docs/api_reference.json src/ai_sw_bridge/sw_types.py
```

生成的 [src/ai_sw_bridge/sw_types.py](src/ai_sw_bridge/sw_types.py) 导出枚举常量（`SW_END_COND_THROUGH_ALL = 1` 等）和一个 `METHOD_SIGNATURES` 字典。构建器在每次 FeatureManager 调用前调用 `assert_args()`，因此任何未来的参数数量偏差都会快速失败并带有清晰的诊断信息。

**经验教训**：当 SW 调用返回 `PARAMNOTOPTIONAL` 或 `Invalid number of parameters` 时，第一件事就是检查参数数量是否匹配 CHM。（[commit c560e97](https://github.com/Thomas-Tai/ai-sw-bridge/commit/c560e97) — `FeatureCut4` 是 27 个参数，不是我们一直发送的 24 个。）

## 当前可构建的内容

三类共八个特征原语。每个原语都支持字面 mm 值和 `{rhs}` 绑定表达式用于任何长度字段，除非"参数化"列另有说明。

**草图**

| 原语 | 参考坐标系 | 参数化 | 限制 |
|---|---|---|---|
| `sketch_rectangle_on_plane` | Front / Top / Right 参考平面 | width, height, center | center 默认 (0, 0) = 零件原点 |
| `sketch_rectangle_on_face` | 早期拉伸体的 +/-z 面 | width, height, center | 仅 +/-z 面；sketch 原点 = 零件原点到面的投影（非面几何中心） |
| `sketch_circle_on_plane` | Front / Top / Right 参考平面 | diameter, center | center 默认 (0, 0) = 零件原点 |
| `sketch_circle_on_face` | 早期拉伸体的 +/-z 面 | diameter | 仅 +/-z 面；圆心位置仅支持 mm（位置不支持 rhs） |
| `sketch_circles_on_face` | 早期拉伸体的 +/-z 面 | 每个圆的 diameter | 相同面限制；多圆 sketch，每个圆一个驱动尺寸 |

**拉伸**

| 原语 | 继承轴来自 | 参数化 | 限制 |
|---|---|---|---|
| `boss_extrude_blind` | 父 sketch（平面或面） | depth | 仅 Blind 终止条件 |
| `cut_extrude_through_all` | 父 sketch | *（无尺寸）* | Through-all 终止条件 |
| `cut_extrude_blind` | 父 sketch | depth | 仅 Blind 终止条件 |

**修改**

| 原语 | 目标 | 参数化 | 限制 |
|---|---|---|---|
| `fillet_constant_radius` | 一个或多个按零件坐标点指定的边 | radius | 仅恒定半径（无变半径/非对称/setback）；边选择按点，无"面的所有边"语法糖 |

完整的每个原语 schema 细节见 [src/ai_sw_bridge/spec/schema.py](src/ai_sw_bridge/spec/schema.py)。涵盖每个原语的完整示例见 [examples/](examples/)。

**验证环境**：SOLIDWORKS 2024 SP1（rev 32.1.0）、Python 3.14、pywin32 late-binding。附带的四个示例（cylinder、MMP、TensionBracket、filleted_box）在 `--no-dim` 模式下均能干净构建。

## 路线图

三个层级，按缺失能力阻碍真实硬件零件的频率与添加成本排列优先级。

**近期（v0.3 — 扩展现有内容）**

接下来的四个原语各自遵循与 v0.2 中 `fillet_constant_radius` 相同的方案：先用 `CreateDefinition` 管线做 spike，仅在该管线失败时回退到单次调用 API。每个原语约 45-60 分钟。

- `+/-x` 和 `+/-y` 面支持用于子 sketch — `_select_extrude_face` 的机械扩展，无新 API
- `fillet_variable_radius`、`chamfer_constant_distance` — 与定半径圆角相同的 `CreateDefinition` 家族
- `simple_hole`（沉孔、埋头孔）— `IFeatureManager.HoleWizard5` 家族
- `linear_pattern`、`circular_pattern`、`mirror` — 对现有特征做阵列；将重复几何折叠为一个 spec 条目

**中期（v0.4 — 扩展零件词汇）**

不同的 SW API 家族，各有自己的设计问题。每个都是多天的工作量，而非分钟级。

- `revolve` — 与拉伸不同的特征家族；需要轮廓 sketch + 旋转轴元素。用于 IdlerRoller、AxleEndCap 及任何车削/旋转零件。
- `sweep` 和 `loft` — 路径驱动；spec 语言需要表达路径几何，而不仅是轮廓。可能需要单独的 `path_sketch` 特征类型。
- 钣金特征 — 基体法兰、边线法兰、绘制的折弯、平板型式。完全独立的 SW UI 模式。
- 参考几何 — 自定义参考平面、轴、点。任何不在 Front/Top/Right 上的拉伸都需要。

**长期（"大部分 SW API"）**

这些各自代表一个子系统，而非一个特征。只有在 v0.3-v0.4 词汇熟悉之后才现实。

- **装配体 + 配合** — `IAssemblyDoc`、`IMate2`、组件放置。目前桥接工具可以*观察*装配体（mate_errors 工具）但不能创建。Propose–Approve–Execute 纪律延续，但 API 表面大约翻倍。
- **工程图** — `IDrawingDoc`、视图放置、尺寸标注、BOM。与零件构建工作基本正交。
- **曲面** — `IFeatureManager.InsertSurface*` 家族。主要由 ID/造型工作使用，机械零件较少。
- **配置** — 多变体零件，每个配置有不同尺寸。涉及每个现有原语（每个都需要一个配置感知变体）。

**不在路线图上**

- VBA 生成 — 作为参数化模式的弹窗抑制回退方案进行了调查；由于 OLE 复合文档打包要求而有风险；见 [docs/known_limitations.md](docs/known_limitations.md)。如果 SW 修复了该版本上的 `swInputDimValOnCreate` toggle 行为，可能会重新考虑。
- 流畅的 Python 构建器 API（`part.box().hole()...`）。JSON spec 是 AI 原生创作表面；链式 API 已被领域调研否决十年。
- 从 pywin32 迁移到 comtypes/pythonnet。Late-binding 对 26 个在用方法中的 26 个都能工作。早期"cut 不可达"的结论是错误的（只是参数数量错误）；不要在错误前提上重建基础。

## 为什么这样设计

- **AI 助手需要可验证、可逆的操作。** 每次修改都是 `propose → dry-run → review → commit`。回滚验证从磁盘读回文件并与快照比较。
- **`*_locals.txt` 文件是唯一真实来源。** 直接在 SW 方程式管理器中编辑变量是脆弱的（链接可能覆盖它们）。我们始终编辑文件，然后重新加载 + 重建。
- **仅支持 pywin32 late-binding。** `EnsureDispatch`/makepy 在大多数安装上对 `SldWorks.Application` 不起作用。我们接受 late-binding 的代价（某些 API 不可达，见已知问题）并设法解决。
- **所有操作都是 JSON 输入/输出。** 可从任何 AI 助手框架轻松脚本化 — Claude Code、OpenAI Assistants、自定义 MCP 服务器、普通 shell 脚本。
- **CHM 是权威的。** API 签名在不同 SW 版本之间会变化。在新的 SW 安装上重新提取；生成的 `sw_types.py` 会自动调整运行时参数数量断言。

## 目录结构

```
ai-sw-bridge/
├── src/ai_sw_bridge/
│   ├── sw_com.py            # SldWorks dispatch + helpers
│   ├── sw_types.py          # 自动生成的枚举常量 + assert_args
│   ├── observe.py           # 阶段 1：只读工具
│   ├── mutate.py            # 阶段 2：Propose-Approve-Execute
│   ├── locals_io.py         # *_locals.txt 解析器 + 原子写入器
│   ├── parameterize.py      # Path C：录制宏参数化器
│   ├── spec/                # v0.2：JSON-spec 构建管线
│   │   ├── schema.py        # spec 语言的 JSON schema
│   │   ├── validator.py     # 3 层验证（schema、引用、locals）
│   │   └── builder.py       # direct-COM 构建执行器
│   └── cli/                 # CLI 入口点
├── tools/
│   ├── chm_extract.py       # 反编译 CHM 签名/枚举解析器
│   ├── gen_api_markdown.py  # JSON → docs/api_reference.md
│   ├── gen_sw_types.py      # JSON → src/ai_sw_bridge/sw_types.py
│   └── _api_extract_input.json  # 要提取的方法/枚举
├── docs/
│   ├── architecture.md                     # 阶段、设计理念（v0.1）
│   ├── ai_driven_architecture_review.md    # 领域调研 + v0.2 计划
│   ├── tools_reference.md                  # 每个 CLI 命令、每个标志
│   ├── known_gotchas.md                    # 我们踩过的坑
│   └── api_reference.{md,json}             # CHM 验证的 SW API 参考
├── examples/
│   ├── minimal_cylinder/        # Path C 示例（录制宏 → 参数化）
│   ├── minimal_cylinder_v2/     # v0.2 示例（JSON spec → direct-COM）
│   └── motor_mount_plate/       # S1b MMP 的 v0.2 spec（部分；v1 限制）
├── spikes/phase0/                # 阶段 0 风险消除 spike + MMP 调试日志
├── USAGE.md
├── CHANGELOG.md
├── pyproject.toml
└── requirements.txt
```

## 许可证

MIT。见 [LICENSE](LICENSE)。

## 致谢

SOLIDWORKS API 模式参考：[CodeStack](https://www.codestack.net/solidworks-api/)。Path C 尺寸绑定修复（`EquationMgr.Add2` 3 参数形式）来自他们的 `document/dimensions/add-equation/` 示例。
