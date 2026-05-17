# 已知限制

> **Language**: [English](../../known_limitations.md) · 简体中文 (简体中文)

编写你的第一个 spec 之前请先阅读本文。每节指出一个尖锐边缘、展示如何识别你已碰到它、并提供解决方案。

关于代码扩展的陷阱（pywin32 marshalling、SW API 怪癖），请另见 [known_gotchas.md](../../known_gotchas.md)。

---

## 1. 面 sketch 原点 = 零件原点投影，**不是**面几何中心

"几何出现在错误位置"类 bug 的最大单一来源。当你通过 `sketch_rectangle_on_face`、`sketch_circle_on_face` 或 `sketch_circles_on_face` 在早期拉伸体的面上 sketch 时，**sketch 局部原点是零件原点投影到该面上的点**，不是面的几何中心。

两者会重合——前提是父拉伸体以零件原点为中心（这正是 MMP 的情况——它的底板是 Front Plane 上通过原点的 `CreateCenterRectangle`）。一旦父拉伸体偏离原点，两者就会产生分歧。

### 如何识别

- 你预期子特征会以面为中心，但它却落在面的边缘（或完全在面之外，产生一个切了一半的孔，或一个悬空的板）。
- `doc.GetPartBox(True)` 显示的 Y 或 X 范围是你预期的 2 倍。
- 视觉上：子方块在父 footprint 的下方恰好突出父相关尺寸的一半。

### 实际案例（TensionBracket §13.3）

Inboard cap 在 spec 中被偏移到零件坐标系 Y ∈ [0, 15]：
```json
{"type": "sketch_rectangle_on_plane", "name": "SK_InboardCap",
 "plane": "Front", "width": 20, "height": 15,
 "center": {"x": 0.0, "y": 7.5}}
```

现在 cap 在零件坐标系 X/Y 的质心是 `(0, 7.5)`，但零件原点是 `(0, 0)`。Cap 的 `+z` 面继承了这一点：面几何中心在零件 `(0, 7.5, 3)`，但面 sketch 原点落在零件 `(0, 0, 3)`。

Cap 上方的 slot slab 需要以 cap 的质心（Y=7.5）为中心，因此它的 spec 必须对 sketch 加上偏移：
```json
{"type": "sketch_rectangle_on_face", "name": "SK_SlotSlab",
 "of_feature": "Extrude_InboardCap", "face": "+z",
 "width": 8.5, "height": 15,
 "center": {"u": 0.0, "v": 7.5}}
```

没有那个 `v: 7.5`，slab 会落在零件 Y ∈ [-7.5, 7.5] 而不是 [0, 15]，bounding box 在 Y 上会是 22.5mm 而不是 15mm。

### 解决方案

1. 在心里追踪你的父拉伸体几何中心在零件坐标系中的位置。
2. 如果不是 `(0, 0)`，对每个子面 sketch 加上 `center: {u: <dx>, v: <dy>}` 字段来补偿。
3. 构建之后，运行 `doc.GetPartBox(True)`（乘以 1000 换算为 mm）并与你预期的尺寸比较。Bounding box 是最便宜的事实核查。

### 运行时检测

当构建器检测到面 sketch 位于非原点对齐的父拉伸体上、且你没有指定 `center` 偏移时，会向 stderr 发出警告。警告包含父面的中心坐标，这样你可以看到默认值是否是你想要的。

---

## 2. 只有拉伸体的 `+/-z` 面能承载子 sketch

构建器中的 `_select_extrude_face` 目前只接好了 `+z` 和 `-z`。如果你写 `"face": "+x"` 或任何 `+/-y` 值，构建器会抛出 `NotImplementedError`。

### 如何识别

```
RuntimeError: v1 only supports +z/-z (out/in board) faces of extrusions; got +x
```

### 解决方案

重新定向父拉伸体，使你想 sketch 的面变成它的 `+z` 或 `-z` 面。由于拉伸体从父 sketch 的参考平面继承轴向，这通常意味着为基础 sketch 选择不同的参考平面：

- 需要在盒子的 +X 面 sketch？把盒子 sketch 在 **Right Plane**（YZ、法线 +X）而不是 Front Plane。这样 +X 面在桥接工具的局部坐标系中就变成了盒子的 `+z` 面。
- 需要同时访问侧面和顶面？你需要将零件拆成两个堆叠的拉伸体，一个的 `+z` 是原来的 `+z`、另一个的 `+z` 是原来的 `+x` — 目前没有干净的方法做到。

### 解除此限制需要什么

机械式扩展：将 `_select_extrude_face` 扩展到在拉伸轴为 `+/-Y` 或 `+/-X` 时计算切平面偏移（目前只接好了 `+/-Z`），并扩展面 sketch 处理器中的 mirror-u 逻辑。估计：含 spec 测试 60-90 分钟。在 [路线图](README.md#roadmap) 的"近期"层级中跟踪。

---

## 3. 参数化模式触发阻塞的 AddDimension2 弹窗

当你运行 `ai-sw-build` 而**没有** `--no-dim` 时，每个有标注尺寸的 sketch 实体都会触发一个"Modify Dimension"弹窗，需要手动鼠标点击才能让构建继续。在 SW 2024 SP1 上，MMP 大小的零件约 16 个弹窗。相关的 `swInputDimValOnCreate` 用户偏好（toggle ID 8）读回是预期的 `False`，但经验证**不会**抑制弹窗。

### 如何识别

`ai-sw-build` 看似卡住。SOLIDWORKS 显示一个带有数字字段和绿/红勾的小型浮动"Modify"对话框。CLI 在等你逐一点击。

### 解决方案

**使用 `--no-dim` 模式**，除非你特别需要生成的 SLDPRT 对 `locals.txt` 有实时方程式链接：

```powershell
ai-sw-build my_spec.json --no-dim
```

在 `--no-dim` 模式中，构建器先在 Python 中对 `spec['locals']` 解析每个 `{"rhs": "..."}` 引用、替换为字面 mm 值、跳过每个 `AddDimension2` 调用。几何会正确产出；SLDPRT 只是没有连回 locals 的方程式。

### 为什么没有修复

在 [spikes/phase0/MMP_DEBUG_SESSION.md](../../../spikes/phase0/MMP_DEBUG_SESSION.md) 和 Spike M / Spike O 扫描中记录了三种失败的抑制方法：

- `SetUserPreferenceToggle(swInputDimValOnCreate=8, False)` — toggle 读回为已设置，弹窗仍然触发
- `SetUserPreferenceToggle(78, False)`（swSketchEnableOnScreenNumericInput 类）— 同样：无效果
- `SendKeys("{ENTER}")` 来消除对话框 — 不会路由到模态子窗口
- 通过 Win32 的 `keybd_event(VK_RETURN)` — 消除浮动弹窗，但 PM 面板仍会阻塞
- 通过可查询的内部 SW dims 完全绕过 AddDimension2（Spike O）— SW 不会自动创建可链接的 dim 对象

论坛上的标准建议（设置 toggle 8）据报道在 SW 自己的 VBA 编辑器内可工作，但在此版本上不会传递到外部 pywin32 COM 客户端。VBA 宏回退（发射 `.bas`、通过 `RunMacro2` 执行）是唯一剩下的途径，并带有自己的风险；见[路线图"不在路线图上"](README.md#roadmap)。

---

## 4. 边选择使用字面零件坐标

Fillet（`fillet_constant_radius`）和任何未来指向边的原语通过边上的 3D 点选择边：

```json
{"type": "fillet_constant_radius", "name": "F", "radius": 2.0,
 "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}]}
```

这是机械式且可预测的，但代表**改变上游尺寸（例如盒子宽度）会把边移到别处，字面边点就不再命中它**。

### 如何识别

`RuntimeError: could not select edge #0 at part (X, Y, Z) mm -- point not on any edge of current geometry`

### 解决方案

当你改变影响边位置的尺寸时，更新 spec 中的字面边坐标来匹配。目前还没有"按索引指定特征 X 的边"的寻址方式。

未来的 `edges_by_face: "+z"` 语法糖（对一个面的所有边做 fillet）会处理常见情况、不需要每条边的坐标；在路线图上但未实现。

---

## 5. 每次 `ai-sw-build` 都会创建一个新的未命名 Part

构建器总是调用 `NewDocument`。它**不会**修改当前活跃的 SOLIDWORKS 文档。构建之后：

- 一个新的"PartN"窗口出现（N 自动递增）。
- 之前活跃的窗口保持不变。
- 新窗口可能不是位于顶层的可见窗口（焦点取决于用户点击了什么）。
- 如果你需要 SLDPRT 保存到磁盘，传入 `--save-as <absolute_path>`。否则零件只存在于内存中，在你关闭 SW（或其窗口）时被丢弃。

这是有意设计的 — 构建是可复现的、不会冒险覆盖手动编辑的工作。但这确实意味着构建之后立刻调用 ai-sw-observe `screenshot` 可能不会显示刚建好的零件，如果焦点当前在不同窗口上。用 `doc.GetTitle` 确认你正在查看的是哪个文档；或通过 `sw.GetFirstDocument` 遍历所有打开的文档。

---

## 6. Schema 验证不会捕获几何不可能性

验证器检查：schema 形状、特征之间的拓扑引用、locals 文件变量的存在性。它**不会**检查：

- 面上的圆是否真的会落在材料上（它可能完全落在先前 cut 留下的空腔中）。
- 圆角半径是否大于最小相邻边。
- 生成的几何是否封闭、有效、合理。

这些失败会在构建过程中以运行时异常的形式浮现（`FeatureCut4 returned None`，或更糟：静默成功的构建带有损坏的几何）。构建后的 bbox 健全性检查是捕获后者最便宜的方法。

---

## 报告新的尖锐边缘

如果你碰到可复现、且不在此列表中的问题，请开一个 issue，附上：spec JSON、完整的 CLI 输出（含 traceback）、SW 版本（帮助 → 关于 → 修订号字符串）、以及（部分）构建后的 `doc.GetPartBox(True)` 输出。
