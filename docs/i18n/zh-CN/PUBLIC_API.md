---
translated-from: e3bec289377be23d6673971dff79ae8c049c7c0c
---

# Public API & Stability Contract（公开 API 与稳定性契约）

> **状态：** ai-sw-bridge 截至 **v1.7.0** 的受支持能力面。
> 未在此列出的一切都属于**内部实现**，可能不经通知就发生变化。

> **开发者能力面 — 契约。** 受支持范围的承诺：每个公开符号、它的稳定性层级、
> SemVer + 弃用策略。面向任务的 **how-to** 食谱见 [`../USAGE.md`](../../../USAGE.md)；
> 详尽的 CLI/MCP **参考** 见 [`tools_reference.md`](../../tools_reference.md)。

这是客户 / 集成方可以依赖的契约。它有三个受支持的能力面 — **CLI**、
**MCP 工具**，以及 **Python 外观 (facade)** — 再加上一份明确的 SemVer 承诺（§4）。
`ai_sw_bridge.*` 之下的其余一切（尤其是
`ai_sw_bridge.features`、`ai_sw_bridge.mutate`、`ai_sw_bridge.observe`、`com`、
`spec`、`brep`、`selection`、`checkpoint`、`resilience` 内部实现）都是**私有**的。

---

## 1. CLI 命令（`[project.scripts]`）

每个命令都声明一个**稳定性层级**，打印在它的 `--help` 横幅中，并由
`tests/test_cli_stability.py` 强制执行：

- **stable** — 未经主版本号跃升不会有破坏性变更。
- **experimental** — 在任何发布版本中都可能变化或被移除。
- **deprecated** — 将在下一个主版本中被移除；每次运行都会打印 stderr 警告。

| 层级 | 命令 |
|---|---|
| **stable** | `ai-sw-build`、`ai-sw-observe`、`ai-sw-mutate`、`ai-sw-assembly`、`ai-sw-drawing`、`ai-sw-properties`、`ai-sw-configurations` |
| **experimental** | `ai-sw-probe`、`ai-sw-batch`、`ai-sw-codegen`、`ai-sw-history`、`ai-sw-apidoc`、`ai-sw-memory`、`ai-sw-checkpoint`、`ai-sw-import`、`ai-sw-export-dxf-flat`、`ai-sw-motion`、`ai-sw-solver`、`ai-sw-urdf`、`ai-sw-sketch-relations`、`ai-sw-sketch-edit`、`ai-sw-doctor` |
| **daemon** | `ai-sw-mcp` — MCP stdio 服务器（不是一个 argparse CLI；见 §2） |

权威的"每命令层级"定义在 `cli/stability.py::TIER_REGISTRY` 以及该命令自己的
`--help` 中。每个可变更命令都遵循 **propose → approve → execute**：AI 绝不会
在没有显式人工确认 / `--yes` 闸门的情况下修改模型。

## 2. MCP 工具（`ai-sw-mcp`）

MCP 服务器暴露的工具集在 `tests/mcp_lane/test_server_contract.py`
（`EXPECTED_TOOLS`）中按**名称与负载形状**被锁定，加上
`tests/mcp_lane/fixtures/` 里逐工具的快照 — 这些测试就是契约，因此一次工具的
增删改名，或负载形状的变化，都会让 CI 大声失败。分组如下：

- **观察类（只读）：** `sw_active_doc`、`sw_feature_errors`、`sw_equations`、
  `sw_bbox`、`sw_volume`、`sw_screenshot`、`sw_measure`、`sw_measure_selection`、
  `sw_mate_errors`、`sw_custom_props`、`sw_enabled_addins`、`sw_interference`、
  `sw_bounding_box`、`sw_inertia`、`sw_clearance`、`sw_draft_analysis`、
  `sw_current_selection`、`sw_undercut_faces`、`sw_min_wall_thickness`、
  `sw_feature_statistics`、`sw_analyze_stackup`、`sw_observe_mbd`。
- **构建 / 批处理：** `sw_build`（校验 → **聊天内 elicit 批准** → 构建；
  没有显式的 `approve=true` 就不会构建或 `save_as`）；`sw_batch_plan`
  （**硬编码 `dry_run=True`** — 永远不能持久化到磁盘）；`sw_batch_execute`
  （PLAN → 聊天内 elicit → COMMIT）。这两个写入工具（`sw_build`、
  `sw_batch_execute`）是仅有的两条能触达磁盘的 MCP 路径，且都由 MCP
  elicitation 做人工把关。
- **API 文档：** `sw_apidoc_search`、`sw_apidoc_detail`、`sw_apidoc_members`、
  `sw_apidoc_examples`、`sw_apidoc_enum`。
- **历史 / 韧性：** `sw_history_part`、`sw_history_since`、
  `sw_history_diff`、`sw_checkpoint_info`、`sw_session_health`（只读）、
  `sw_reconnect`。
- **Design-Memory（RAG）：** `sw_retrieve_design_memory`（本地，设备端）。

**自主写入安全性：** 没有任何 MCP 工具会在未经明确聊天内人工批准的情况下
持久化到磁盘。两个写入工具（`sw_build`、`sw_batch_execute`）都会把它们的
COM 写入置于 MCP elicitation 的 `approve=true` 之后；`sw_batch_plan` 从设计上
就只做计划、不做持久化。由 `tests/mcp_lane/test_build_elicit.py` +
`test_batch_execute.py`（那个 COM 写入可调用对象只在获得批准时才会被调用）
以及 `test_server_contract.py` 中的 `COM_SAFE_VIA_MANUAL_DISPATCH` 契约固定。

## 3. Python 外观 (facade)

```python
from ai_sw_bridge.client import SolidWorksClient
sw = SolidWorksClient()                 # lazy, injectable app/module
sw.observe. ...                         # read lanes
sw.mutate.batch(path, proposals)        # supervised-by-default write (v1.6.0)
sw.export. ... / sw.urdf. ...           # export lanes
```

`SolidWorksClient`（连同它的 `.observe` / `.mutate` / `.export` / `.urdf` /
`.features` 域外观）是**唯一受支持的 Python 入口点**。这个包同时也重新导出了
纯 Python 工具（`locals_io`、`parameterize`、`spec`）供非 Windows 场景使用。
v1.0 时移除的那些自由 `sw_*` 函数已经不存在了；剩下的模块私有的 `_*_impl`
核心**不是**公开 API。

## 4. SemVer 与兼容性承诺

在一个主版本（`1.x`）内：

- **保证向后兼容：** **stable** 层级 CLI 命令的标志 + 双流（stdout-JSON /
  stderr-text）契约；**MCP 工具名称 + I/O 负载形状**（`EXPECTED_TOOLS`
  契约）；**`SolidWorksClient` 外观**的方法签名。
- **可能在次版本发布中变化：** **experimental** 层级 CLI 命令；
  `ai_sw_bridge.features.*` 之下的一切，以及所有其他 `_internal`/`_impl`
  模块；磁盘上的检查点 / 事务台账格式。
- **弃用：** 被标记为 `deprecated` 的一个 stable 能力面，会在宣布弃用所在的
  那整条 `1.x` 线上持续可用，并发出警告，具体依据下方的**弃用策略**与
  **稳定性层级**两节。

对一个受保证的能力面做破坏性变更，需要一次**主版本**跃升（`2.0.0`）。

## 5. 冻结的集成契约

以下是打包与下游集成方所绑定的不变量。每一条都已经由一个既有测试强制
执行 — 本节只是人类可读的索引，不是新的检查。

- **控制台脚本名称。** 22 个 `ai-sw-*` 入口点（`ai-sw-probe`、
  `ai-sw-observe`、`ai-sw-mutate`、`ai-sw-batch`、`ai-sw-assembly`、
  `ai-sw-drawing`、`ai-sw-properties`、`ai-sw-configurations`、
  `ai-sw-sketch-relations`、`ai-sw-sketch-edit`、`ai-sw-codegen`、
  `ai-sw-build`、`ai-sw-history`、`ai-sw-apidoc`、`ai-sw-memory`、
  `ai-sw-checkpoint`、`ai-sw-import`、`ai-sw-export-dxf-flat`、
  `ai-sw-motion`、`ai-sw-solver`、`ai-sw-urdf`、`ai-sw-doctor`）加上 `ai-sw-mcp`，
  全部定义在 `[project.scripts]`（`pyproject.toml`）中，并指向
  `ai_sw_bridge.cli.*` / `ai_sw_bridge.mcp.server`。对这些名称中任何一个的
  重命名、移除，或目标模块变更，都是一次破坏性的打包变更。
  由 `tests/test_doc_truth.py`（`_cli_command_count` 直接从 `pyproject.toml`
  推导出数量，并锁定每一处复述该数量的文档表面）强制执行。
- **CLI 退出码契约。** `ai-sw-build`（`src/ai_sw_bridge/cli/build.py`）
  只会返回 `0`（成功）、`2`（参数 / 规格文件 / 标志错误）、`3`
  （schema 校验失败）、`4`（构建失败，或被 `--strict-addins`
  拦截）、`5`（`--dry-run` 的 rhs 解析失败）、`6`（`--lint` 有发现）、
  或 `7`（`--auto-retry` 拒绝了一次完全相同的重复提交）之一 —
  **绝不会是 `1`**（`1` 是其他 CLI 共用的通用 `ok:false` 代码，例如
  `ai-sw-batch` / `ai-sw-checkpoint`，而不属于 `ai-sw-build`）。
  由 `tests/cli/test_exit_codes_documented.py` 强制执行，它锁定了
  `docs/tools_reference.md` 的 "Exit codes" 一节记录了代码 `3`–`7`，
  且仍然提到 `stderr`（座席横幅正是写在那里的）。
- **MCP 工具名称集合。** `ai-sw-mcp` 服务器的工具能力面（名称 +
  负载形状）由 `tests/mcp_lane/test_server_contract.py` 中的
  `EXPECTED_TOOLS` 锁定 — 目前是 §2 中列出的观察 / 构建-批处理 /
  API-文档 / 历史-韧性 / design-memory 各分组共 37 个工具。一次工具的
  增删改名，或负载形状的变化，都会让那个测试失败（并进而让
  `tests/test_doc_truth.py` 的 `_mcp_tool_count` 失败 — 它导入
  `EXPECTED_TOOLS` 来保持每一处文档计数同步）。

---

## 稳定性层级（按命令）

_合并自原先的 `cli_stability.md`。_


每一个 `ai-sw-bridge` CLI 入口点都声明一个明确的稳定性层级。
该层级会以 `[tier]` 前缀出现在 `--help` 输出的描述行中，并被追踪在一个
模块级注册表中（`cli/stability.py` 中的 ``TIER_REGISTRY``），测试可以检视它。

## 层级定义

| 层级           | 向后兼容承诺                                                    |
|----------------|------------------------------------------------------------------------|
| **stable**     | 未经主版本号跃升（1.x → 2.0），CLI 标志、位置参数或 JSON 输出     |
|                | 形状不会有破坏性变更。新增可选标志、新增输出键等增量式改动       |
|                | 允许出现在任何发布版本中。     |
| **experimental**| 在任何发布版本中都可能变化或消失。输出形状和标志名称  |
|                | 不受保证。生产环境中使用需自行承担风险。               |
| **deprecated** | 将在下一个主版本发布中被移除。每次调用都会发出 stderr 警告    |
|                | 。                                                   |

## 如何新增一个层级

1. 导入装饰器与辅助函数：

   ```python
   from .stability import add_tier, cli_stability
   ```

2. 装饰你的 ``main()`` 函数：

   ```python
   @cli_stability("stable")
   def main() -> int:
       ...
   ```

3. 在 ``ArgumentParser`` **构造之后**调用 ``add_tier()``：

   ```python
   parser = argparse.ArgumentParser(...)
   add_tier(parser, "stable")
   ```

4. 测试套件会强制要求 ``src/ai_sw_bridge/cli/`` 中每一个带
   ``main()`` 函数的 CLI 模块都有一个明确的层级 — 一个没有层级的新子命令
   会让 ``test_all_cli_modules_registered`` 失败。

## 当前分配情况

权威的"每命令层级"分配存放在 `TIER_REGISTRY`
（`cli/stability.py`）中，并体现在每个命令自己的 `--help` 横幅里。完整的
stable / experimental / daemon 逐命令细分见上方 §1 — 本节刻意不再保留手工
维护的副本（它此前已经漂移到 22 个命令里只有 5 个是对的，本说明取代了
那份副本）。

---

## 弃用策略

_合并自原先的 `deprecation_policy.md`。_


ai-sw-bridge 如何移除东西，以及规格格式如何演进。存在本节的原因是让
下游的规格与集成永远不会在没有预警的情况下被破坏。（Enhancement plan P3.2。）

### 语义化版本

包版本号（`pyproject.toml`）遵循 [SemVer](https://semver.org/)：

- **MAJOR** — 对规格 schema 或 CLI / MCP / facade 契约（标志、退出码、
  JSON 输出键、工具名称、签名）的向后不兼容变更。
- **MINOR** — 向后兼容的新功能（新的特征基本操作类型、新标志、
  新工具）。
- **PATCH** — 向后兼容的缺陷修复。

### 按能力面类别划分的宽限期

向后兼容性以及移除前的宽限期，取决于该能力面的稳定性类别：

| 能力面类别 | 在何处宣布（deprecated） | 硬性移除 | 宽限期下限 |
|---|---|---|---|
| **Stable** — CLI（层级 `stable`）、MCP 工具、`SolidWorksClient` 外观签名 | `1.N` | **只在下一个主版本，`2.0`** | 从宣布到 `2.0` 切割点之间 ≥ 2 个次版本发布 |
| **Experimental** — CLI（层级 `experimental`）、规格处理器 | `1.N` | `1.N+1` | 1 个次版本发布 |

Stable 能力面在宣布弃用所在的那个主版本内**绝不会**被移除。这套宽限期算法
由 `src/ai_sw_bridge/deprecations.py` + `tests/test_deprecations.py` 机器强制执行：
CI 闸门会拒绝任何 `remove_in` 不是下一个主版本边界（stable）或下一个次版本
（experimental）的注册条目。

### 弃用流程

任何面向用户的东西都不会在没有经过弃用周期的情况下被移除：

1. **宣布。** 将被移除的东西 — 一个 CLI 标志、一个 JSON 输出键、一个
   特征类型、一个公开函数 — 会通过 `warnings.warn(..., DeprecationWarning)`
   发出一个 `DeprecationWarning`，并被列在 `CHANGELOG.md` 的一个
   `### Deprecated` 标题下。警告中会指名替代方案。
2. **宽限期。** 它会在上表所述的下限期间内持续可用 — 对 stable 能力面来说
   是那整条 `1.x` 线，对 experimental 能力面来说至少一个次版本。
3. **移除。** 移除会落在之后某个发布版本的 `CHANGELOG.md` `### Removed`
   标题下。

一次跳过警告周期的移除是一个 bug，而不是一次正常发布。

### 弃用警告（MCP 工具）

当一个 MCP 工具被弃用时，警告会出现在两条通道上（这是策略；实际的运行时
接线要等到第一个真正的 MCP 工具弃用案例出现时才会落地 — 目前还没有已弃用
的工具可以拿来练手）：

- **人类可读** — 工具描述会被加上 `[DEPRECATED in 1.N → use X]` 前缀，
  在工具发现阶段可见。
- **机器可读** — 一个 `_deprecation: {replaces: "X", remove_in: "2.0"}`
  区块会被注入该工具 JSON 响应信封中，供无界面消费者使用。

CLI 弃用会在每次调用时向 stderr 发出一个 `DeprecationWarning`；Python
外观弃用会发出 `DeprecationWarning`（在宣布窗口期内则是
`PendingDeprecationWarning`）。

## 规格 `schema_version` 迁移

规格格式带有一个整数型 `schema_version`（目前是 `1`，以
`schema.SCHEMA_VERSION` 的形式暴露）：

- 校验器**只**接受 `schema_version` 等于当前 `SCHEMA_VERSION` 的规格；
  不匹配时会立即快速失败并给出清晰的错误。
- **增量式**变更（新增可选字段、新增特征类型）**不会**让 `schema_version`
  跃升 — 既有的规格保持有效。
- 一次**破坏性**的规格变更（字段被重命名/移除、语义变更）会把
  `schema_version` 跃升到下一个整数，并在同一个发布版本中一并交付：
  - 新的 `SCHEMA_VERSION` 常量，
  - 一个 `tools/migrate_spec.py` 一次性转换器（例如 `v1 -> v2`），
  - 一条指向该转换器的 `### Changed` CHANGELOG 条目。
- 该转换器至少会被保留一个 MAJOR 发布版本，让线上流通的规格仍然能够被
  升级。

在需要 `schema_version: 2` 之前，本节就是一份长期有效的正式承诺：
**规格绝不会被悄悄破坏。**
