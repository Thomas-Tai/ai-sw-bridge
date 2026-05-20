---
translated-from: c8ce816
---

# 已知限制

> **Language**: [English](../../../docs/known_limitations.md) · 简体中文

在编写你的第一份规格之前，请先阅读本文。每个章节说明一个坑、如何识别你踩到了，以及替代方案。

关于代码库扩展的注意事项（pywin32 封送处理、SW API 异常行为），请参阅 [known_gotchas.md](known_gotchas.md)。

---

## 1. 面草图原点 = 零件原点投影，不是面质心

"几何出现在错误位置"bug 的最大来源。当你通过 `sketch_rectangle_on_face`、`sketch_circle_on_face` 或 `sketch_circles_on_face` 在先前拉伸的面上绘制草图时，**草图局部原点位于零件原点投影到该面上的位置**，而不是面的几何中心。

如果父拉伸体以零件原点为中心（这正是 MMP 的做法 — 其底板是在 Front Plane 上穿过原点的 `CreateCenterRectangle`），两者会重合。一旦父拉伸体偏离原点，两者就会分岔。

### 如何识别

- 你预期子特征在面上居中，但它却出现在面的边缘（或完全超出面，产生半切的孔或悬空的板）。
- `doc.GetPartBox(True)` 显示的 Y 或 X 范围是你预期的 2 倍。
- 视觉上：子方块向下突出超出父体底面刚好半个父体的相关尺寸。

### 实际示例（TensionBracket §13.3）

内侧盖板在规格中偏移，使其落在零件框架 Y ∈ [0, 15]：
```json
{"type": "sketch_rectangle_on_plane", "name": "SK_InboardCap",
 "plane": "Front", "width": 20, "height": 15,
 "center": {"x": 0.0, "y": 7.5}}
```

现在盖板在零件框架 X/Y 中的质心是 `(0, 7.5)`，但零件原点在 `(0, 0)`。盖板的 `+z` 面继承了这一点：面几何中心在零件 `(0, 7.5, 3)`，但面草图原点落在零件 `(0, 0, 3)`。

盖板顶部的槽板需要居中于盖板的质心（Y=7.5），因此其规格必须偏移草图：
```json
{"type": "sketch_rectangle_on_face", "name": "SK_SlotSlab",
 "of_feature": "Extrude_InboardCap", "face": "+z",
 "width": 8.5, "height": 15,
 "center": {"u": 0.0, "v": 7.5}}
```

如果没有那个 `v: 7.5`，槽板会落在零件 Y ∈ [-7.5, 7.5] 而非 [0, 15]，边界框会变成 Y 方向 22.5mm 而非 15mm。

### 替代方案

1. 在脑中追踪你的父拉伸体几何中心在零件坐标中的位置。
2. 如果不是 `(0, 0)`，在每个子面草图中加入 `center: {u: <dx>, v: <dy>}` 字段来补偿。
3. 构建完成后，执行 `doc.GetPartBox(True)`（乘以 1000 得到 mm）并与你预期的尺寸比对。边界框是最便宜的现实检查。

### 运行时检测

当构建器检测到非原点对齐的父体上的面草图，且你未指定 `center` 偏移时，会向 stderr 发出警告。警告包含父体的面中心坐标，让你可以判断默认值是否是你想要的。

---

## 2. 只有拉伸体的 `+/-z` 面可以承载子草图

构建器中的 `_select_extrude_face` 目前只接了 `+z` 和 `-z`。如果你写 `"face": "+x"` 或任何 `+/-y` 值，构建器会抛出 `NotImplementedError`。

### 如何识别

```
RuntimeError: v1 only supports +z/-z (out/in board) faces of extrusions; got +x
```

### 替代方案

重新调整父拉伸体的方向，使你想绘制草图的面成为其 `+z` 或 `-z` 面。由于拉伸会继承父草图参考平面的轴向，这通常意味着为基础草图选择不同的参考平面：

- 需要在方块的 +X 面上绘制草图？在 **Right Plane**（YZ，法线 +X）而非 Front Plane 上绘制方块草图。这样 +X 面就成为方块在桥接器局部框架中的 `+z` 面。
- 需要侧面和顶面都可访问？你需要将零件拆成两个堆叠的拉伸体，一个的 `+z` 是原始的 `+z`，另一个的 `+z` 是原始的 `+x` — 目前没有简洁的做法。

### 移除此限制需要什么

机械层面：扩展 `_select_extrude_face` 以在拉伸轴为 `+/-Y` 或 `+/-X` 时（目前只接了 `+/-Z`）计算切平面偏移，并扩展面草图处理器中的 mirror-u 逻辑。估计：60-90 分钟，包含规格测试。已跟踪于 [Roadmap](../../../README.md#roadmap) 的"近期"层级。

---

## 3. 参数化模式会触发阻塞式 AddDimension2 弹窗

当你运行 `ai-sw-build` 时**不**加 `--no-dim`，每个有标注尺寸的草图实体都会触发一个"Modify Dimension"弹窗，需要手动点一下才能继续构建。在 SW 2024 SP1 上，一个 MMP 规模的零件大约有 16 个弹窗。相关的 `swInputDimValOnCreate` 用户偏好（切换 ID 8）读回的值是预期的 `False`，但实际上并未抑制弹窗。

### 如何识别

`ai-sw-build` 看起来像卡住了。SOLIDWORKS 显示一个小型浮动的"Modify"对话框，带有数值字段和绿色/红色勾选。CLI 正在等你逐一点过每一个。

### 替代方案

**使用 `--no-dim` 模式**，除非你特别需要在生成的 SLDPRT 中有到 `locals.txt` 的实时方程式链接：

```powershell
ai-sw-build my_spec.json --no-dim
```

在 `--no-dim` 模式下，构建器会在 Python 中预先将每个 `{"rhs": "..."}` 参考解析对应到 `spec['locals']`，替换为字面 mm 值，并跳过每个 `AddDimension2` 调用。几何结果正确；SLDPRT 只是没有连回 locals 的方程式。

### 为什么这个问题尚未修复

三种失败的抑制方法记录于 [spikes/phase0/MMP_DEBUG_SESSION.md](../../../spikes/phase0/MMP_DEBUG_SESSION.md) 以及 Spike M / Spike O 扫描中：

- `SetUserPreferenceToggle(swInputDimValOnCreate=8, False)` — 切换读回值为已设置，弹窗仍然出现
- `SetUserPreferenceToggle(78, False)`（swSketchEnableOnScreenNumericInput 类别）— 同样：无效
- `SendKeys("{ENTER}")` 关闭对话框 — 无法路由到模态子窗口
- `keybd_event(VK_RETURN)` 通过 Win32 — 可以关闭浮动弹窗，但 PM 窗格仍阻塞
- 完全绕过 AddDimension2，改用可查询的内部 SW 尺寸（Spike O）— SW 不会自动创建可链接的尺寸对象

论坛上公认的建议（设置切换 8）据报在 SW 自身的 VBA 编辑器中有效，但不会传播到此版本上的外部 pywin32 COM 客户端。VBA 宏回退方案（输出 `.bas`，通过 `RunMacro2` 执行）是唯一剩余的途径，但也有其自身的风险；参见 [Roadmap "Not on the roadmap"](../../../README.md#roadmap)。

### 第二个替代方案：`--deferred-dim`

`--deferred-dim` 为你提供实时方程式链接，但弹窗点击是**每个草图时间局部化**的（单个草图的所有弹窗连续出现，中间没有 COM 调用延迟），而非交错分散在多分钟的几何阶段中：

```powershell
ai-sw-build my_spec.json --deferred-dim
```

在此模式下，几何以占位尺寸构建，不调用 `AddDimension2`；在每个草图处理器返回后，桥接器立即通过 `EditSketch` 重新进入草图，在一个会话中重放所有 `AddDimension2` 调用，然后应用特征的 `EquationMgr.Add2` 链接并重建。

**每个尺寸仍需点一次弹窗按钮。** 每个 `AddDimension2` 调用仍会因一个手动"Modify Dimension"弹窗而阻塞。弹窗总数与**默认内联模式相同** — 每个有尺寸的实体一个按钮。用户可感知的改善是*时机*，而非*数量*：

- 内联模式：弹窗 → 数秒 COM 调用 → 弹窗 → 数秒 COM 调用 → ...（弹窗散布在整个构建过程中）
- `--deferred-dim`：仅 COM 的几何构建（无弹窗）→ 草图 A 的 N 个连续弹窗 → 草图 B 的仅 COM 构建 → 草图 B 的 M 个连续弹窗 → ...

你仍然点相同数量的弹窗。它们只是以可预测的集群到达，中间穿插仅 COM 的构建阶段。

如果你需要零弹窗，请使用 `--no-dim`（无方程式链接）。不存在同时提供实时链接和零弹窗的第四种模式 — 在测试了 12 种候选抑制路径后已经实证证伪（参见 [deferred_dim_investigation.md](deferred_dim_investigation.md)）。

**矩形支持（已于 2026-05-20 修复，Spike ZF）：** 矩形草图（`sketch_rectangle_on_plane`、`sketch_rectangle_on_face`）先前在 SW 2024 SP1 上的第二个边尺寸会被降级为从动 (driven)，破坏了该尺寸的方程式链接。根本原因：API 端的 `CreateCenterRectangle` 会加入一个 UI 绘制等价物中不存在的多余 Midpoint 关系，将 2-DOF 坍缩为 1-DOF。修复是 [`builder.py`](../../../src/ai_sw_bridge/spec/builder.py) 中的 `_strip_centerrectangle_midpoint_relation()`，从两个矩形处理器在 `CreateCenterRectangle()` 之后立即调用。矩形规格现在在三种模式（默认内联、`--deferred-dim`、`--no-dim`）下都能提供完整的方程式链接。已在 `motor_mount_plate` 端到端验证，D1 和 D2 都正确驱动其 `S1B_MMP_H`/`S1B_MMP_W` 链接。

Spike 轨迹 Z1–ZF（2026-05-19 至 2026-05-20）探索了 11 条缓解路线，最终 ZF 通过用户 UI 检查找到了根本原因。以下路线无效并记录供历史参考：逐草图尺寸分组、构造对角线删除、`IDisplayDimension.DrivenState` 覆写（通过 pywin32 及通过 VBA 注入器 — 两者皆不可达）、编辑中 `EditRebuild3`、手动 `CornerRectangle` + Midpoint、`gencache.EnsureModule` 依明确 GUID、`MakeSelectedDriving`、`LinkValue` 属性、`Add3` 搭配 `swAllConfiguration`、`SetEquationAndConfigurationOption`、内联尺寸搭配延迟链接。

---

## 4. 边选择使用字面零件坐标

圆角（`fillet_constant_radius`）及任何未来的边目标基本操作通过边上的 3D 点来选择边：

```json
{"type": "fillet_constant_radius", "name": "F", "radius": 2.0,
 "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}]}
```

这是机械性且可预测的，但这意味着**改变上游尺寸（例如方块宽度）可能使边移到其他位置，而字面边点将不再命中它。**

### 如何识别

`RuntimeError: could not select edge #0 at part (X, Y, Z) mm -- point not on any edge of current geometry`

### 替代方案

当你改变影响边位置的尺寸时，更新规格中的字面边坐标以匹配。目前尚无"按索引取特征 X 的边"的寻址方式。

未来的 `edges_by_face: "+z"` 语法糖（圆角化一个面的所有边）可以处理常见情况而无需逐边坐标；已在路线图上但尚未实现。

---

## 5. 每次运行 `ai-sw-build` 都会创建新的未命名 Part

构建器一律调用 `NewDocument`。它不会修改当前活动的 SOLIDWORKS 文档。构建完成后：

- 出现一个新的"PartN"窗口（N 会自动递增）。
- 先前活动的窗口保持不变。
- 新窗口可能不是最上层的可见窗口（焦点取决于用户点击了什么）。
- 如果你需要将 SLDPRT 存到磁盘，传入 `--save-as <绝对路径>`。否则零件只存在于内存中，关闭 SW（或其窗口）时即会丢失。

这是刻意的 — 构建是可重现的，不会冒覆盖手动编辑工作的风险。但这确实意味着在构建后立即运行 ai-sw-observe `screenshot` 调用时，如果其他窗口目前有焦点，可能不会显示刚构建的零件。使用 `doc.GetTitle` 确认你正在检查哪个文档；或遍历 `sw.GetFirstDocument` 枚举所有打开的文档。

---

## 6. Schema 验证不会捕捉几何不可能的情况

验证器检查：schema 形状、特征之间的拓扑引用、locals 文件变量是否存在。它不检查：

- 面上的圆是否实际落在材料上（它可能完全位于先前切除的空隙中）。
- 圆角半径是否大于最小相邻边。
- 生成的几何是否封闭、有效或合理。

这些失败在构建过程中以运行时异常呈现（`FeatureCut4 returned None`，或更糟，一个静默成功但几何损坏的构建）。构建后的边界框健全性检查是捕捉后者最便宜的方式。

---

## 报告新发现的坑

如果你遇到了可重现且不在本列表中的问题，请开一个 issue，附上：规格 JSON、完整的 CLI 输出（包含跟踪信息）、SW 版本（Help → About → 修订字符串），以及（部分）构建后的 `doc.GetPartBox(True)` 输出。
