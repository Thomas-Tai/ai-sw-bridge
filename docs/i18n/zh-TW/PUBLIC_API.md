---
translated-from: e3bec289377be23d6673971dff79ae8c049c7c0c
---

# 公開 API 與穩定性合約

> **狀態：** ai-sw-bridge 截至 **v1.7.0** 的支援範圍。
> 未列於此處的一切都是**內部**實作，可能隨時變更且不另行通知。

> **開發者介面 — 合約 (Contract)。** 支援範圍的承諾：每一個公開
> 符號、它的穩定性分級、SemVer + 淘汰政策。若要查閱任務導向的
> **操作指南**請見 [`../USAGE.md`](USAGE.md)；若要查閱鉅細靡遺的 CLI/MCP
> **參考文件**請見 [`tools_reference.md`](../../tools_reference.md)。

這是客戶／整合者可以仰賴的合約。它有三個支援範圍 — **CLI**、**MCP
工具**、以及 **Python 外觀 (facade)** — 加上一份明確的 SemVer 承諾（§4）。
`ai_sw_bridge.*` 之下的其他所有東西（特別是
`ai_sw_bridge.features`、`ai_sw_bridge.mutate`、`ai_sw_bridge.observe`、`com`、
`spec`、`brep`、`selection`、`checkpoint`、`resilience` 內部實作）都是**私有**的。

---

## 1. CLI 指令（`[project.scripts]`）

每個指令都宣告一個**穩定性分級**，印在它的 `--help` 橫幅裡，並由
`tests/test_cli_stability.py` 強制驗證：

- **stable** — 沒有主版號升級就不會有破壞性變更。
- **experimental** — 任何版本都可能變更或被移除。
- **deprecated** — 下一個主版號會移除；每次執行都會印出 stderr 警告。

| 分級 | 指令 |
|---|---|
| **stable** | `ai-sw-build`、`ai-sw-observe`、`ai-sw-mutate`、`ai-sw-assembly`、`ai-sw-drawing`、`ai-sw-properties`、`ai-sw-configurations` |
| **experimental** | `ai-sw-probe`、`ai-sw-batch`、`ai-sw-codegen`、`ai-sw-history`、`ai-sw-apidoc`、`ai-sw-memory`、`ai-sw-checkpoint`、`ai-sw-import`、`ai-sw-export-dxf-flat`、`ai-sw-motion`、`ai-sw-solver`、`ai-sw-urdf`、`ai-sw-sketch-relations`、`ai-sw-sketch-edit`、`ai-sw-doctor` |
| **daemon** | `ai-sw-mcp` — MCP stdio 伺服器（不是 argparse CLI；見 §2） |

權威的「每指令分級」定義在 `cli/stability.py::TIER_REGISTRY` 及
該指令自己的 `--help`。每個會變更狀態的指令都遵循 **propose → approve →
execute**：AI 絕不會在沒有明確人為 / `--yes` 閘門的情況下變更模型。

## 2. MCP 工具（`ai-sw-mcp`）

MCP 伺服器公開一組被**名稱與 payload 結構**釘住的工具，釘在
`tests/mcp_lane/test_server_contract.py`（`EXPECTED_TOOLS`）+ `tests/mcp_lane/fixtures/`
下的逐工具快照 — 這些測試就是合約，所以工具的
新增／移除／重新命名，或 payload 結構的變更，都會讓 CI 大聲失敗。分組如下：

- **觀察（唯讀）：** `sw_active_doc`、`sw_feature_errors`、`sw_equations`、
  `sw_bbox`、`sw_volume`、`sw_screenshot`、`sw_measure`、`sw_measure_selection`、
  `sw_mate_errors`、`sw_custom_props`、`sw_enabled_addins`、`sw_interference`、
  `sw_bounding_box`、`sw_inertia`、`sw_clearance`、`sw_draft_analysis`、
  `sw_current_selection`、`sw_undercut_faces`、`sw_min_wall_thickness`、
  `sw_feature_statistics`、`sw_analyze_stackup`、`sw_observe_mbd`。
- **建構／批次：** `sw_build`（驗證 → **聊天內 elicit 核准** → 建構；
  沒有明確的 `approve=true` 就不會建構或 `save_as`）；`sw_batch_plan`
  （**硬性寫死 `dry_run=True`** — 絕不可能寫入磁碟）；`sw_batch_execute`
  （PLAN → 聊天內 elicit → COMMIT）。這兩個寫入工具（`sw_build`、
  `sw_batch_execute`）是唯二會碰到磁碟的 MCP 路徑，兩者都由 MCP
  elicitation 做人為把關。
- **API 文件：** `sw_apidoc_search`、`sw_apidoc_detail`、`sw_apidoc_members`、
  `sw_apidoc_examples`、`sw_apidoc_enum`。
- **歷史／韌性：** `sw_history_part`、`sw_history_since`、
  `sw_history_diff`、`sw_checkpoint_info`、`sw_session_health`（唯讀）、
  `sw_reconnect`。
- **設計記憶（RAG）：** `sw_retrieve_design_memory`（本機端、裝置端運算）。

**自動化寫入的安全性：** 沒有任何 MCP 工具會在沒有明確聊天內人為
核准的情況下寫入磁碟。兩個寫入工具（`sw_build`、`sw_batch_execute`）都把
它們的 COM 寫入動作把關在一個 MCP elicitation `approve=true` 之後；`sw_batch_plan`
本質上就是純規劃、不會寫入。由 `tests/mcp_lane/test_build_elicit.py` +
`test_batch_execute.py` 釘住（COM 寫入的可呼叫物件只有在核准後才會被呼叫），以及
`test_server_contract.py` 中的 `COM_SAFE_VIA_MANUAL_DISPATCH` 合約。

## 3. Python 外觀 (facade)

```python
from ai_sw_bridge.client import SolidWorksClient
sw = SolidWorksClient()                 # lazy, injectable app/module
sw.observe. ...                         # read lanes
sw.mutate.batch(path, proposals)        # supervised-by-default write (v1.6.0)
sw.export. ... / sw.urdf. ...           # export lanes
```

`SolidWorksClient`（以及它的 `.observe` / `.mutate` / `.export` / `.urdf` /
`.features` 領域外觀）是**唯一支援的 Python 進入點**。這個套件也重新匯出
純 Python 的工具函式（`locals_io`、`parameterize`、`spec`）供非 Windows 環境使用。
在 v1.0 被移除的自由函式 `sw_*` 已經不存在；剩下的
模組私有 `_*_impl` 核心**不是**公開介面。

## 4. SemVer 與相容性承諾

在同一個主版本（`1.x`）內：

- **保證向後相容：** **stable** CLI 指令的旗標 + 雙串流
  （stdout-JSON / stderr-文字）合約；**MCP 工具名稱 + I/O
  payload 結構**（`EXPECTED_TOOLS` 合約）；**`SolidWorksClient`
  外觀**的方法簽章。
- **可能在小版本更新中變更：** **experimental** CLI 指令；`ai_sw_bridge.features.*`
  之下的一切，以及所有其他 `_internal`/`_impl` 模組；
  磁碟上 checkpoint／交易帳本的格式。
- **淘汰：** 一個標記為 `deprecated` 的 stable 介面，在該版本宣告淘汰後，
  會在整個 `1.x` 系列中持續可用並發出警告，依循下方的**淘汰
  政策**與**穩定性分級**章節。

對一個保證介面的破壞性變更，需要一次**主版號**升級（`2.0.0`）。

## 5. 凍結的整合合約

這些是套件與下游整合者所仰賴的不變量。每一項都已經被一個
既有測試強制驗證 — 這一節只是給人類看的索引，不是新增的檢查。

- **Console-script 名稱。** 22 個 `ai-sw-*` 進入點（`ai-sw-probe`、
  `ai-sw-observe`、`ai-sw-mutate`、`ai-sw-batch`、`ai-sw-assembly`、
  `ai-sw-drawing`、`ai-sw-properties`、`ai-sw-configurations`、
  `ai-sw-sketch-relations`、`ai-sw-sketch-edit`、`ai-sw-codegen`、
  `ai-sw-build`、`ai-sw-history`、`ai-sw-apidoc`、`ai-sw-memory`、
  `ai-sw-checkpoint`、`ai-sw-import`、`ai-sw-export-dxf-flat`、
  `ai-sw-motion`、`ai-sw-solver`、`ai-sw-urdf`、`ai-sw-doctor`）加上 `ai-sw-mcp`，全部定義
  在 `[project.scripts]`（`pyproject.toml`）中，並指向
  `ai_sw_bridge.cli.*` / `ai_sw_bridge.mcp.server`。對這些指令中任何一個
  重新命名、移除，或變更目標模組，都是破壞性的封裝變更。
  由 `tests/test_doc_truth.py` 強制驗證（`_cli_command_count` 直接從
  `pyproject.toml` 推算數量，並釘住每一份文件中重述這個數字的地方）。
- **CLI 結束代碼合約。** `ai-sw-build`（`src/ai_sw_bridge/cli/build.py`）
  只會回傳 `0`（成功）、`2`（參數／規格檔／旗標錯誤）、`3`
  （schema 驗證失敗）、`4`（建構失敗，或 `--strict-addins`
  擋下）、`5`（`--dry-run` 的 rhs 解析失敗）、`6`（`--lint` 有
  發現項目）、或 `7`（`--auto-retry` 拒絕了一次相同的重複提交） —
  **絕不會是 `1`**（`1` 是其他 CLI 共用的通用 `ok:false` 代碼，例如
  `ai-sw-batch` / `ai-sw-checkpoint`，不是 `ai-sw-build` 用的）。
  由 `tests/cli/test_exit_codes_documented.py` 強制驗證，該測試釘住
  `docs/tools_reference.md` 的「Exit codes」章節記載了代碼
  `3`–`7`，且仍提到 `stderr`（seat 橫幅會寫到那裡）。
- **MCP 工具名稱集合。** `ai-sw-mcp` 伺服器的工具介面（名稱 +
  payload 結構）由 `tests/mcp_lane/test_server_contract.py` 中的
  `EXPECTED_TOOLS` 釘住 — 目前是橫跨 §2 上方所列觀察／建構批次／
  API 文件／歷史韌性／設計記憶各分組的 37 個工具。工具的
  新增／移除／重新命名，或 payload 結構變更，都會讓那個測試失敗（並連帶讓
  `tests/test_doc_truth.py` 的 `_mcp_tool_count` 失敗，它會匯入
  `EXPECTED_TOOLS` 以讓每一份文件的計數保持同步）。

---

## 穩定性分級（依指令）

_整併自舊的 `cli_stability.md`。_


每一個 `ai-sw-bridge` CLI 進入點都宣告一個明確的穩定性分級。
這個分級會以 `[tier]` 前綴出現在 `--help` 輸出的描述行，
並被追蹤在一個模組層級的註冊表中
（`cli/stability.py` 中的 ``TIER_REGISTRY``），供測試檢查。

## 分級定義

| 分級           | 向後相容承諾                                                    |
|----------------|------------------------------------------------------------------------|
| **stable**     | 沒有主版號升級（1.x → 2.0）就不會對 CLI 旗標、位置參數，     |
|                | 或 JSON 輸出結構做破壞性變更。任何版本都可以新增       |
|                | （新的選用旗標、新的輸出鍵）。     |
| **experimental**| 任何版本都可能變更或消失。輸出結構與旗標名稱  |
|                | 不受保證。正式環境使用風險自負。               |
| **deprecated** | 下一個主版號會被移除。每次呼叫    |
|                | 都會印出一則 stderr 警告。                                                   |

## 如何新增一個分級

1. 匯入裝飾器與輔助函式：

   ```python
   from .stability import add_tier, cli_stability
   ```

2. 裝飾你的 ``main()`` 函式：

   ```python
   @cli_stability("stable")
   def main() -> int:
       ...
   ```

3. 在 ``ArgumentParser`` **建構之後**呼叫 ``add_tier()``：

   ```python
   parser = argparse.ArgumentParser(...)
   add_tier(parser, "stable")
   ```

4. 測試套件會強制驗證 ``src/ai_sw_bridge/cli/`` 底下每一個有
   ``main()`` 函式的 CLI 模組都有明確的分級 — 一個
   沒有分級的新子指令會讓 ``test_all_cli_modules_registered`` 失敗。

## 目前的分配

權威的「每指令分級」分配住在 `TIER_REGISTRY`
（`cli/stability.py`），並顯示在每個指令自己的 `--help` 橫幅裡。完整的
stable / experimental / daemon 分類請見上方 §1 — 這一節刻意不維護
手動同步的副本（在被這則說明取代之前，它已經在 22 個指令中漂移到只剩 5 個是同步的）。

---

## 淘汰政策

_整併自舊的 `deprecation_policy.md`。_


ai-sw-bridge 如何移除東西，以及規格格式如何演進。這一節
存在的目的，是確保下游規格與整合不會在毫無預警的情況下被打斷。
（Enhancement plan P3.2。）

### 語意化版本

套件版本（`pyproject.toml`）遵循 [SemVer](https://semver.org/)：

- **MAJOR** — 對規格 schema 或 CLI / MCP
  / 外觀合約（旗標、結束代碼、JSON 輸出鍵、工具名稱、簽章）的破壞性變更。
- **MINOR** — 向後相容的新功能（新的特徵基本操作、新的旗標、
  新的工具）。
- **PATCH** — 向後相容的錯誤修正。

### 依介面等級劃分的緩衝期

向後相容性，以及移除前的緩衝期，取決於介面所屬的
穩定性等級：

| 介面等級 | 於何時宣告淘汰 (deprecated) | 何時硬性移除 | 緩衝期下限 |
|---|---|---|---|
| **Stable** — CLI（`stable` 分級）、MCP 工具、`SolidWorksClient` 外觀簽章 | `1.N` | **只會在下一個主版號 `2.0`** | 宣告到 `2.0` 切分之間 ≥ 2 個小版本 |
| **Experimental** — CLI（`experimental` 分級）、規格處理器 | `1.N` | `1.N+1` | 1 個小版本 |

Stable 介面**絕不會**在宣告淘汰的那個主版本內被移除。這個緩衝期算法
由 `src/ai_sw_bridge/deprecations.py` + `tests/test_deprecations.py` 機械式
強制驗證：CI 閘門會拒絕任何 `remove_in` 不是下一個主版號邊界
（stable）或下一個小版本（experimental）的登記項目。

### 淘汰程序

任何面向使用者的東西都不會在沒有淘汰週期的情況下被移除：

1. **宣告。** 要被移除的東西 — 一個 CLI 旗標、一個 JSON 輸出鍵、一個
   特徵類型、一個公開函式 — 會透過
   `warnings.warn(..., DeprecationWarning)` 發出 `DeprecationWarning`，並
   列在 `CHANGELOG.md` 的 `### Deprecated` 標題下。警告訊息會
   指名替代方案。
2. **緩衝期。** 它會在上方的緩衝期下限內持續可用 — 對 stable 介面來說
   是整個 `1.x` 系列，對 experimental 來說至少一個小版本。
3. **移除。** 移除動作會在之後某個版本的 `CHANGELOG.md` 中，登記於
   `### Removed` 之下。

跳過警告週期的移除是一個錯誤，不是一次合法的發布。

### 淘汰警告（MCP 工具）

當一個 MCP 工具被淘汰時，警告會出現在兩個管道上（這是政策；
實際的執行期接線會隨第一個真正被淘汰的 MCP 工具一起實作 —
目前沒有已淘汰的工具可以拿來驗證）：

- **人類可讀** — 工具描述會加上 `[DEPRECATED in 1.N → use X]` 前綴，
  在工具探索時可見。
- **機器可讀** — 一個 `_deprecation: {replaces: "X", remove_in: "2.0"}`
  區塊會被注入該工具的 JSON 回應封套中，供無介面消費者使用。

CLI 的淘汰會在每次呼叫時於 stderr 發出 `DeprecationWarning`；Python
外觀的淘汰會發出 `DeprecationWarning`（或在宣告期間發出
`PendingDeprecationWarning`）。

## 規格 `schema_version` 遷移

規格格式帶有一個整數型的 `schema_version`（目前是 `1`，以
`schema.SCHEMA_VERSION` 公開）：

- 驗證器**只**接受 `schema_version` 等於目前
  `SCHEMA_VERSION` 的規格；不相符會立即快速失敗並給出清楚的錯誤訊息。
- **附加性**的變更（新的選用欄位、新的特徵類型）**不會**
  提升 `schema_version` — 既有規格依然有效。
- **破壞性**的規格變更（欄位重新命名／移除、語意變更）
  會把 `schema_version` 提升到下一個整數，並在同一個版本中一併發布：
  - 新的 `SCHEMA_VERSION` 常數，
  - 一個一次性的 `tools/migrate_spec.py` 轉換器（例如 `v1 -> v2`），
  - 一則指向該轉換器的 `### Changed` CHANGELOG 條目。
- 該轉換器至少會保留一個 MAJOR 版本，讓現存的規格
  依然能被升級。

在強制要求 `schema_version: 2` 之前，這一節就是目前的
承諾方向：**絕不悄悄破壞規格。**
