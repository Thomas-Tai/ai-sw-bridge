---
translated-from: c8ce816
---

# 为什么 `--no-dim` 存在：AddDimension2 弹窗事后剖析

> **Language**: [English](../../why_no_addim2.md) · 简体中文

> 目标读者：未来的工程师（人类或 AI），那些忍不住想"修好"
> AddDimension2 弹窗阻塞器的人。本文记录了我们尝试了什么、什么
> 失败了、以及为什么，让你不用重走同样的死路。

## TL;DR

`IModelDoc2.AddDimension2` 会打开一个 Modify-Dimension 弹窗，在 SW 2024 SP1 上**无法通过 pywin32 抑制**。我们交付了 `ai-sw-build --no-dim`，它会在 Python 中预先将 `{"rhs": "..."}` 参考解析对应到 `spec['locals']`，并跳过每个 `AddDimension2` 调用。取舍：生成的 SLDPRT 没有到 `locals.txt` 的实时方程式链接（重新运行 `ai-sw-build` 以传播编辑）。

**如果你是因为有人告诉你"只要把 `swInputDimValOnCreate` 设为 False"而来 — 请继续读。我们试过了。三次。在此版本上从外部 COM 客户端是无效的。**

## 问题

`AddDimension2(x, y, z)` 是 SW 将数值绑定到草图尺寸的方式，让 `EquationMgr.Add2` 之后可以按名称（例如 `"D1@SK_Body"`）定位。在 SW 2024 SP1 上，每次调用会打开**两个**对话框：

1. 一个小型浮动的 **Modify Dimension 弹窗**（数值 + 绿色/红色勾选）
2. 左侧的 **Dimension PropertyManager (PM) 窗格**（绿色/红色勾选）

两者都必须关闭后 `AddDimension2` 才会返回。此调用同步阻塞 — COM 线程停住直到用户点击。实测约**每个尺寸 ~12 秒**的人力注意。对于 MMP（约 15 个尺寸），每次构建约 ~30 次点击。

## 我们尝试了什么以及每种方法失败的原因

| 方法 | 实验 | 结果 | 失败原因 |
|---|---|---|---|
| 切换 8（`swInputDimValOnCreate`）`SetUserPreferenceToggle(8, False)` | [spike_i_verify_toggle.py](../../../spikes/phase0/spike_i_verify_toggle.py) | 失败 | `GetUserPreferenceToggle(8)` 在 Set 调用前后都读回 False，但 `AddDimension2` 仍阻塞 ~12 秒。可能是 ID 8 在此版本上不是 `swInputDimValOnCreate`，或者该偏好根本不从外部 COM 上下文管控 `AddDimension2`。 |
| 切换 78（`swSketchEnableOnScreenNumericInput` 类别，论坛建议为"真正的"切换） | [spike_m_toggle_78.py](../../../spikes/phase0/spike_m_toggle_78.py) | 失败 | 结果与切换 8 相同。Pywin32 + SW 2024 SP1 两者皆忽略。 |
| `keybd_event(VK_RETURN)` 盲注入 | [spike_h_sendkeys.py](../../../spikes/phase0/spike_h_sendkeys.py) | 部分有效 | 盲 keybd_event 确实能关闭 Modify 弹窗，但 PM 窗格仍保持焦点。双重 ENTER（间隔 200ms）不可靠 — 第一个 ENTER 关闭弹窗后，焦点回到启动终端，第二个 ENTER 不会落在 SW 中。`sw.SendKeys("{ENTER}")` 和 keybd_event + `SetForegroundWindow` 都完全失败（焦点从模态窗口被抢到主窗口）。 |
| `doc.Extension.RunCommand(1, "")` 关闭 PM 窗格 | [spike_f_close_pm.py](../../../spikes/phase0/spike_f_close_pm.py) | 失败 | 返回 True 但窗格仍然打开。`doc.ClosePropertyManager()` 和 `doc.Extension.CloseAndDestroyPropertyManagers()` 都抛出 AttributeError（在此版本上不是成员）。 |
| `AddSpecificDimension`（AddDimension2 的类型替代方案） | [spike_j_specific_dim.py](../../../spikes/phase0/spike_j_specific_dim.py) | 失败 | 全部 9 个 `DimType` 值（1-9）返回 `com_error('Type mismatch.', ..., 5)`，每个约 0.1 秒。OUT `Error` 参数无法通过 pywin32 晚期绑定绑定 — 与 `SelectByID2` 的 `Callout` 参数同类失败（参见 [known_gotchas.md](../../known_gotchas.md)）。此方法在此客户端上无法使用。 |
| 查询内部 `D1`/`D2`/`Diameter@...` 尺寸参数**而不**调用 AddDimension2 | [spike_o_param_without_dim.py](../../../spikes/phase0/spike_o_param_without_dim.py) | 失败 | 对 `--no-dim` 圆柱探测了 9 个候选名称。全部 9 个返回 None。SW 不会自动在草图/特征上创建可查询的尺寸参数；通过 `EquationMgr.Add2` 的可链接性需要一个命名尺寸，而这需要 AddDimension2。 |

附注：SW 2024 SP1 主窗口类不是 `"SldWorks"` — 而是 `Afx:*` 类。标题前缀 `"SOLIDWORKS"` 可用于 `FindWindow`。记录于此，以防下次尝试基于焦点的替代方案时需要用到。

## 为什么社区建议不适用

至少有三个独立的社区公认建议（angelsix/codestack/论坛）指向 `swInputDimValOnCreate`（切换 8）作为 Modify-Dim 弹窗的修复方案。它们有效 — 但**仅在 SW 的 VBA 编辑器内部**，在那里切换值在同一个进程 / COM 上下文中与尺寸创建一起生效。从 SW 2024 SP1 上的**外部 pywin32 COM 客户端**，切换 8 和切换 78 都无效。实验 I 和 M 独立确认了这一点。

这是我们部署上下文（外部 Python 进程通过晚期绑定 COM 驱动 SW）特有的病理情况，不是 API 的误用。

## 我们改为交付了什么：`--no-dim`

当设置 `ai-sw-build --no-dim` 时，规格中的每个 `{"rhs": "..."}` 参考会在**任何 SW 调用之前**于 Python 中解析对应到 `spec['locals']`。字面 mm 值替换到规格中，几何以字面目标尺寸构建，每个 `AddDimension2` 调用以及整个 `EquationMgr.Add2` 链接阶段都被跳过。

实现：
- `_load_locals_map`、`_eval_rhs`、`_resolve_rhs_in_spec` 在
  [src/ai_sw_bridge/spec/builder.py](../../../src/ai_sw_bridge/spec/builder.py)
 （第 117-203 行）。处理带引号的变量引用（`"VAR"`）、算术运算和递归 locals（一个变量引用另一个）。循环会抛出异常；未知引用会抛出 KeyError。
- `BuildContext` 新增了 `no_dim: bool` 字段；每个特征处理器在其 `AddDimension2` 代码块上用 `if not ctx.no_dim` 做条件判断。
  几何创建路径不变。
- CLI 标志接线在 [src/ai_sw_bridge/cli/build.py](../../../src/ai_sw_bridge/cli/build.py)。

在 SW 2024 SP1 上的验证：
- 圆柱 `--no-dim`：**1.72 秒，0 次点击**，Ø25 × 80mm 验证通过
- MMP `--no-dim`：**~3 秒，0 次点击，10/10 特征**，截图验证通过
  （参数化模式约 ~60 秒 + ~16 次点击）

**取舍**：生成的 SLDPRT 没有到 `locals.txt` 的方程式链接。
编辑 `locals.txt` 不会传播到现有零件；用户必须重新运行 `ai-sw-build`。locals 文件仍然是唯一的事实来源 — 只是在构建时解析而非运行时。

## 尚未探索的路径

未来的工程师可能会走的路：

- **VBA 宏回退方案。** 每次构建输出一个 `.bas`，然后通过 `RunMacro2` 从 SW 的 VBA 上下文内部调用它，切换 8 在那里可能实际有效。估计成本：~1-2 小时，包含 `.swp` 打包调查（`RunMacro2` 不能直接使用纯文本 `.bas` — 参见 [../CHANGELOG.md](../../../CHANGELOG.md) 中的 v0.1 已知限制）。这恢复了完整的可链接性。

- **切换 ID 探测扫描。** 已编写但未运行
  [spike_n_toggle_discovery.py](../../../spikes/phase0/spike_n_toggle_discovery.py)。
  将暴力探测 4 个候选切换 ID（8、78、95、167），搭配新文档循环。跳过是因为实验 I + M 共同表明切换方法在 pywin32 层**无论哪个 ID 是"正确的"**都已死路。可能结果：更多无效切换。

- **不同的 SW 版本。** SW 2025+ 可能有不同行为 — 我们尚未在其他版本上重现此问题。未测试。

## 如果你忍不住想再试一次切换 8

别试。

我们有**三个**实验产物证明它在此版本上无效（[spike_i_verify_toggle.py](../../../spikes/phase0/spike_i_verify_toggle.py)、
[spike_m_toggle_78.py](../../../spikes/phase0/spike_m_toggle_78.py)、
[spike_o_param_without_dim.py](../../../spikes/phase0/spike_o_param_without_dim.py)）。
切换读回值是你设置的值，但 `AddDimension2` 仍阻塞 ~12 秒等待手动点击。

正确的前进路线是：
- **`--no-dim`** 用于 AI 驱动的构建（不需要实时可链接性）
- **VBA 宏回退方案** 用于确实需要到 `locals.txt` 的实时方程式链接的罕见情况

如果你必须重新调查，请先完整阅读
[../spikes/phase0/MMP_DEBUG_SESSION.md](../../../spikes/phase0/MMP_DEBUG_SESSION.md)
— 上面的每条死路都可以从 [../spikes/phase0/](../../../spikes/phase0/) 中的实验脚本重现。
