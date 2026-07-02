---
translated-from: da2e933cf33b28fe70d1c4a3bde378d2429254e1
---

# USAGE

> **開發者介面 — 操作指南 (How-to guide)。** 這是驅動橋接器的
> 任務導向食譜集。若要查閱鉅細靡遺的 CLI **參考文件**（每個旗標、子指令、payload）
> 請見 [`docs/tools_reference.md`](../../tools_reference.md)；若要查閱
> 支援範圍**合約**（穩定性分級、SemVer、淘汰政策）
> 請見 [`docs/PUBLIC_API.md`](./PUBLIC_API.md)。

ai-sw-bridge 的詳細工作流程。安裝方式與 60 秒快速入門，請見 [README.md](./README.md)。

## 工作流程 1 — 設計指南驗證（唯讀）

使用情境：你寫了一份設計指南，內容說「立柱高度是 `D_Z_BELT − S1B_BELT_T − S1B_ROLLER_DIA/2 = 61.0 mm`」。你想驗證 SOLIDWORKS 是否真的算出這個結果。

```powershell
# 1. 在 SOLIDWORKS 中開啟零件。
# 2. 確認方程式如預期計算：
ai-sw-observe equations > equations.json

# 3.（選用）擷取螢幕截圖以比對視覺參考：
ai-sw-observe screenshot --filename=verification.png
```

輸出的 JSON 包含每一條方程式與其目前的數值。把它接到 `jq`，或直接餵給一個 AI 代理去比對書面指南。

這個工作流程實際用在 Lego Sorter V2 S1b 輸送帶設計指南上，抓到一個參數強制執行的落差（一個應該綁定到 `-"S1B_CHUTE_OUTLET_LOCAL_X"` 卻寫成字面值 `-32.5` mm 偏移量的錯誤）。單看指南文字看不出這個錯誤 — AI 代理是靠比對即時的 `equations` 輸出與已記載的不變量差異才找到的。

## 工作流程 2 — 變更單一變數（Propose-Approve-Execute）

使用情境：設計指南寫著 `S1B_FOOT_W` 應該是 16 mm，但模型上是 15 mm。你想安全地套用這項變更。

**前置條件**：目前開啟的 SW 零件必須有一個透過 Tools → Equations → Link to file 連結的 `*_locals.txt` 檔案。橋接器會讀取 `EquationMgr.FilePath` 找出連結的檔案。

```powershell
# 1. 提案（尚未變更任何 SW 狀態）
ai-sw-mutate propose --var=S1B_FOOT_W --new_value=16.0
# -> proposal_id: a1b2c3d4e5f6, state: proposed

# 2. Dry-run：套用、重建、擷取、回滾
ai-sw-mutate dry_run --proposal_id=a1b2c3d4e5f6
# -> before: { manager_status: 0, var_value: 15.0 }
#    after:  { manager_status: 0, var_value: 16.0 }
#    rebuild_ok: true, rolled_back: true, state: dry_run_ok

# 3. 檢視結果。滿意的話就提交：
ai-sw-mutate commit --proposal_id=a1b2c3d4e5f6
# -> state: committed, doc_saved: true|false
```

`doc_saved: false` 不是錯誤。它代表目前開啟的零件沒有使用這個被變更的變數，所以 SW 沒有東西可寫。`*_locals.txt` 檔案「有」被更新 — 那才是真相來源。

要回滾最後一次提交：
```powershell
ai-sw-mutate undo_last_commit
```

提案紀錄會持久化到 `./proposals/`（可用 `AI_SW_BRIDGE_PROPOSALS` 環境變數覆寫）。你可以用任何 JSON 檢視器查看它們。

## 工作流程 3 — Path C：參數化零件建立

使用情境：你想在 SOLIDWORKS 中把 `MyPart.SLDPRT` 建模一次，之後透過編輯 `*_locals.txt` 重新產生變體。

### 步驟 1：撰寫變數

在你的 `*_locals.txt`（你其他零件已經連結的那個檔案）中，定義這個零件會用到的變數。範例：
```
"PART_DIAMETER"  = 25.0
"PART_LENGTH"    = 80.0
```

### 步驟 2：在 SOLIDWORKS 中錄製零件

1. *File → New → Part*（全新的空零件 — 這很重要；見 [known_gotchas.md](../../known_gotchas.md)）
2. *Tools → Macro → Record*
3. 建構零件。使用**字面值**（例如圓的直徑輸入 `25`，而不是 `="PART_DIAMETER"`）。參數化工具之後會替你替換。
4. **重新命名你的草圖與特徵**成你認得出來的穩定名稱（右鍵 → Feature Properties，或按 F2）。例如 `Sketch1` → 保留原名（或改名為 `SK_Body`）、`Boss-Extrude1` → 改名為 `Extrude_Body`。
5. *Tools → Macro → Stop*。另存為 `recorded.swp`。

### 步驟 3：撰寫規格 JSON

```json
{
  "locals_path": "C:\\path\\to\\your_locals.txt",
  "bindings": [
    { "dim": "D1@Sketch1",      "var": "PART_DIAMETER" },
    { "dim": "D1@Extrude_Body", "var": "PART_LENGTH"   }
  ]
}
```

`dim` 路徑使用 SW 內部的尺寸命名方式：`D<n>@<feature_name>`。你可以在 SW 的方程式管理員中看到這些。如果草圖在錄製過程中被重新命名，請使用**最終**名稱（重新命名之後的） — 繫結是在重新命名之後才執行的，所以路徑反映的是新名稱。

### 步驟 4：參數化

```powershell
ai-sw-codegen parameterize recorded.swp spec.json
```

輸出結果是緊鄰 `.swp` 旁的一個 `.bas` 檔（純文字 VBA）。

### 步驟 5：在 SW 中執行

1. *File → New → Part*（全新的空文件 — 與你錄製時相同的起始狀態）
2. *Alt+F11* 開啟 VBE
3. 把 `recorded_parameterized.bas` 的內容貼進一個新模組（或刪除預設 `Module1` 的樣板後貼進去）
4. 按 F5
5. 點掉任何「modify dimension」彈窗（未來版本會抑制這些彈窗）

### 步驟 6：驗證

```powershell
ai-sw-observe equations | findstr "D1@"
```

尋找你新增的兩筆項目：
```
"D1@Sketch1" = "PART_DIAMETER"     value=25.0
"D1@Extrude_Body" = "PART_LENGTH"  value=80.0
```

現在這個零件是真正參數化的。編輯 `your_locals.txt`、儲存、在 SW 中重建（`Ctrl+B`），零件就會更新。

## 工作流程 4 — 跨 session 的 AI 驅動

因為每個 CLI 都只向 stdout 印出一個 JSON 物件，AI 代理可以不需要任何特殊框架就驅動橋接器：

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

對 Claude Code 及其他 MCP 用戶端來說，`ai-sw-bridge` 提供一個原生 MCP 伺服器 — `ai-sw-mcp` — 透過 stdio 公開 37 個工具（讀取通道 + plan/elicit 把關的寫入）；你不需要自己包一層 CLI。設定方式、工具清單、協定細節請見 [`docs/mcp_server_design.md`](../../mcp_server_design.md)。上面示範的「透過 subprocess 呼叫 CLI」模式，對偏好自訂框架的人來說依然可行。

## 輸出路徑與環境

| 預設位置 | 覆寫方式 |
|---|---|
| `./captures/`（螢幕截圖） | `AI_SW_BRIDGE_CAPTURES=...` 環境變數 |
| `./proposals/`（變更提案） | `AI_SW_BRIDGE_PROPOSALS=...` 環境變數 |

兩個資料夾都會在第一次使用時自動建立。如果不想把它們提交進版本庫，請加進 `.gitignore`。
