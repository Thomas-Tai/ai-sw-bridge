---
translated-from: da2e933cf33b28fe70d1c4a3bde378d2429254e1
---

# USAGE

> **开发者能力面 — How-to 指南。** 面向任务的驱动桥接器食谱。要查阅详尽的 CLI
> **参考**（每个标志、子命令、负载）见 [`docs/tools_reference.md`](../../tools_reference.md)；
> 要查阅受支持范围的**契约**（稳定性层级、SemVer、弃用策略）
> 见 [`docs/PUBLIC_API.md`](./PUBLIC_API.md)。

ai-sw-bridge 的详细工作流。安装方式与 60 秒快速入门见 [README.md](./README.md)。

## 工作流 1 — 设计指南校验（只读）

用例：你写了一份设计指南，其中写道 "the post height is `D_Z_BELT − S1B_BELT_T − S1B_ROLLER_DIA/2 = 61.0 mm`"。你想验证 SOLIDWORKS 是否真的算出这个结果。

```powershell
# 1. Open the part in SOLIDWORKS.
# 2. Check the equation evaluated as expected:
ai-sw-observe equations > equations.json

# 3. (optional) Capture a screenshot to compare against a visual reference:
ai-sw-observe screenshot --filename=verification.png
```

输出的 JSON 包含每一条方程式及其当前的数值。可以把它交给 `jq`，也可以直接喂给一个负责与书面指南比对的 AI 代理。

这个工作流已在 Lego Sorter V2 S1b conveyor 设计指南上实际用过，用来抓出一个参数化落实上的漏洞（一个本应绑定到 `-"S1B_CHUTE_OUTLET_LOCAL_X"` 却写成字面量 `-32.5` mm 偏移的地方）。仅靠阅读指南本身是看不出这个错误的 — AI 代理是通过把实时的 `equations` 输出与文档记录的不变量做差异比对才找到的。

## 工作流 2 — 修改单个变量（Propose-Approve-Execute）

用例：设计指南说 `S1B_FOOT_W` 应该是 16 mm，但模型里是 15 mm。你想安全地应用这个改动。

**前提条件**：当前活动的 SW 零件必须通过 Tools → Equations → Link to file 链接了一个 `*_locals.txt` 文件。桥接器通过 `EquationMgr.FilePath` 来发现这个被链接的文件。

```powershell
# 1. Propose (no SW state changed yet)
ai-sw-mutate propose --var=S1B_FOOT_W --new-value=16.0
# -> proposal_id: a1b2c3d4e5f6, state: proposed

# 2. Dry-run: apply, rebuild, capture, roll back
ai-sw-mutate dry_run --proposal-id=a1b2c3d4e5f6
# -> before: { manager_status: 0, var_value: 15.0 }
#    after:  { manager_status: 0, var_value: 16.0 }
#    rebuild_ok: true, rolled_back: true, state: dry_run_ok

# 3. Inspect the result. If happy, commit:
ai-sw-mutate commit --proposal-id=a1b2c3d4e5f6
# -> state: committed, doc_saved: true|false
```

`doc_saved: false` **不是**错误。它的意思是当前活动零件没有用到被改动的变量，所以 SW 没有东西可写。`*_locals.txt` 文件**确实**被更新了 — 那才是事实来源。

要回滚上一次提交：
```powershell
ai-sw-mutate undo_last_commit
```

提议记录持久化在 `./proposals/` 中（可通过 `AI_SW_BRIDGE_PROPOSALS` 环境变量覆盖）。你可以用任意 JSON 查看器检查它们。

## 工作流 3 — Path C：参数化零件创建

用例：你想在 SOLIDWORKS 里为 `MyPart.SLDPRT` 建模一次，之后通过编辑 `*_locals.txt` 来重新生成各种变体。

### 步骤 1：定义变量

在你的 `*_locals.txt`（你其他零件已经链接的那个文件）中，定义这个零件将要消费的变量。示例：
```
"PART_DIAMETER"  = 25.0
"PART_LENGTH"    = 80.0
```

### 步骤 2：在 SOLIDWORKS 中录制零件

1. *File → New → Part*（一个全新的空零件 — 这一点很重要；见 [known_gotchas.md](../../known_gotchas.md)）
2. *Tools → Macro → Record*
3. 构建这个零件。使用**字面值**（例如圆的直径输入 `25`，而不是 `="PART_DIAMETER"`）。参数化器之后会替你把这些换掉。
4. **把你的草图和特征重命名**为你能认得出的稳定名字（右键 → Feature Properties，或按 F2）。例如 `Sketch1` → 保留原名（或重命名为 `SK_Body`），`Boss-Extrude1` → 重命名为 `Extrude_Body`。
5. *Tools → Macro → Stop*。保存为 `recorded.swp`。

### 步骤 3：编写规格 JSON

```json
{
  "locals_path": "C:\\path\\to\\your_locals.txt",
  "bindings": [
    { "dim": "D1@Sketch1",      "var": "PART_DIAMETER" },
    { "dim": "D1@Extrude_Body", "var": "PART_LENGTH"   }
  ]
}
```

`dim` 路径使用 SW 内部的尺寸命名方式：`D<n>@<feature_name>`。你可以在 SW 的方程式管理器里看到这些名字。如果草图在录制过程中被重命名了，就使用**最终**名称（重命名之后的）— 绑定是在重命名之后运行的，所以路径反映的是新名字。

### 步骤 4：参数化

```powershell
ai-sw-codegen parameterize recorded.swp spec.json
```

输出是紧挨着 `.swp` 的一个 `.bas` 文件（纯文本 VBA）。

### 步骤 5：在 SW 中运行

1. *File → New → Part*（一个全新的空文档 — 与你录制时的起始状态相同）
2. *Alt+F11* 打开 VBE
3. 把 `recorded_parameterized.bas` 的内容粘贴到一个新模块里（或者先删掉默认 `Module1` 里的桩代码再粘贴进去）
4. 按 F5
5. 逐一点掉任何 "modify dimension" 弹窗（未来版本会抑制这些弹窗）

### 步骤 6：验证

```powershell
ai-sw-observe equations | findstr "D1@"
```

寻找你新增的两个条目：
```
"D1@Sketch1" = "PART_DIAMETER"     value=25.0
"D1@Extrude_Body" = "PART_LENGTH"  value=80.0
```

现在这个零件已经是真正参数化的了。编辑 `your_locals.txt`、保存、在 SW 中重建（`Ctrl+B`），零件就会随之更新。

## 工作流 4 — 跨会话 AI 驱动

因为每个 CLI 都只向 stdout 打印一个 JSON 对象，AI 代理不需要任何特殊的载体就能驱动桥接器：

```python
import subprocess, json

def call_bridge(*args):
    result = subprocess.run(
        ["ai-sw-observe", *args],
        capture_output=True, text=True, check=False,
    )
    return json.loads(result.stdout), result.returncode

data, code = call_bridge("equations")
if data["manager_status_code"] != 0:
    print("Equation manager has errors:", data["manager_status"])
```

对于 Claude Code 及其他 MCP 客户端，`ai-sw-bridge` 提供了一个原生 MCP 服务器 — `ai-sw-mcp` — 通过 stdio 暴露 37 个工具（只读通道 + 计划 / elicit 把关的写入通道）；你不需要自己去包装这些 CLI。安装方式、工具清单以及协议细节见 [`docs/mcp_server_design.md`](../../mcp_server_design.md)。上面展示的"通过子进程调用 CLI"这种模式，对于偏好这种方式的自定义载体来说依然可用。

## 输出路径与环境

| 默认位置 | 通过什么覆盖 |
|---|---|
| `./captures/`（截图） | `AI_SW_BRIDGE_CAPTURES=...` 环境变量 |
| `./proposals/`（变更提议） | `AI_SW_BRIDGE_PROPOSALS=...` 环境变量 |

两个文件夹都会在首次使用时自动创建。如果不想把它们提交到版本库，请加入 `.gitignore`。
