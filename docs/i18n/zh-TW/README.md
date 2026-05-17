# ai-sw-bridge

> **Language**: [English](../../../README.md) · Traditional Chinese (繁體中文)

一個半自動化的橋接工具，讓 AI 助理（Claude、ChatGPT、Codex 等）能透過 COM API 驅動 SOLIDWORKS。

## 它做什麼

目前 ai-sw-bridge 提供 **四項能力**，沿著從觀察到 AI 驅動建立的連續光譜：

| 能力 | CLI | 你會得到什麼 |
|---|---|---|
| **檢視** | `ai-sw-observe` | 以 JSON 形式讀取特徵、方程式、配對、螢幕擷取。任何時候執行都安全。 |
| **變數變更** | `ai-sw-mutate` | 對 `*_locals.txt` 變數採用 Propose–Approve–Execute 流程。在 commit 之前先 dry-run 並可回滾。 |
| **錄製巨集參數化**（Path C） | `ai-sw-codegen` | 在 SW UI 中錄製一次，針對 `*_locals.txt` 參數化，重播以重新產生。 |
| **宣告式零件合成**（v0.2，進行中） | `ai-sw-build` | 取得描述特徵與參數化綁定的 JSON spec，透過 direct-COM 驅動 SW 來產生零件。**AI 原生的撰寫路徑。** |

長期目標是第四項能力：AI 代理讀取設計指南、產出 JSON 零件 spec、驅動 SOLIDWORKS 建構它、並驗證結果 —— 全部透過可 diff、可版本控制的工件。Phase 0 與 1 已落地；MMP（motor mount plate）是部分的端對端示範。完整計畫請見 [docs/ai_driven_architecture_review.md](../../ai_driven_architecture_review.md)。

設計圍繞 **Propose–Approve–Execute** 紀律：每次變更都先以 dry-run 配合回滾執行、呈現差異、僅在明確核可後才 commit。AI 永遠不會取得對你 CAD 模型的「可隨意操作」按鈕。

## 目前狀態（2026-05-17）

**v0.1 能力 — 在 SOLIDWORKS 2024 SP1 上經過正式驗證**：
- `ai-sw-probe`、`ai-sw-observe`、`ai-sw-mutate` 端對端可運作
- Path C 參數化已在單一 extrude 圓柱上驗證

**v0.2 能力 — Phase 1 GREEN：**
- Phase 0 spikes：**GREEN** —— direct-COM late-binding 對 v0.2 架構是可行的
- Phase 1（JSON-spec builder）：**GREEN**
  - 圓柱範例可端對端建構並含參數化綁定
  - **Motor Mount Plate (MMP) 端對端建出 10/10 個特徵** 並含 7 個參數化綁定（50×50 板配置同心 Ø12 聯軸器孔 + Ø20.5 法蘭凹槽 + 馬達/框架孔對於 ±15mm）。幾何驗證為置中。
- **CHM 驗證過的 API 參考**（[docs/api_reference.md](../../api_reference.md)）—— 從官方 `sldworksapi.chm` 擷取 23 個使用中的 SW 方法 + 5 個 enum，並在執行階段斷言參數數量

## 為什麼這件事重要

**打造 AI 驅動的 SOLIDWORKS 自動化是真正的 R&D。** SW 社群花了十年打造 add-in 框架（angelsix、xCAD、codestack）與僅修改用的 wrapper（pyswx、pySldWrap），但沒有人交付過宣告式的零件建構器。ai-sw-bridge 的 v0.2 工作就是這個缺口 —— 請見 [docs/ai_driven_architecture_review.md](../../ai_driven_architecture_review.md) 中的領域調查。

讓它在現在變得可行的原因：

- **AI 助理擅長 JSON。** Spec 是純資料，不是 VBA 散文。AI 寫 spec，bridge 執行它。
- **透過 pywin32 late-binding 的 direct-COM 在我們測試過的 build 上對大部分 SW API 都能運作。** 「cuts 不行」的教訓是錯的（請見 commit `c560e97`）—— 一旦你傳給 FeatureCut4 它期待的全部 27 個參數（而非舊文件暗示的 24 個）就能正常運作。
- **權威的 API 簽章。** 當 SW 呼叫返回 `PARAMNOTOPTIONAL` 時，第一件要檢查的事就是參數數量是否符合 `sldworksapi.chm`。我們把這個查詢編碼化；請見 [tools/chm_extract.py](../../../tools/chm_extract.py)。

## 限制（採用前請先讀）

**平台與 API**

- **僅 Windows。** SOLIDWORKS 僅支援 Windows，且 `pywin32` 僅支援 Windows。
- **僅 pywin32 late-binding。** `EnsureDispatch`/makepy 在大多數安裝上對 `SldWorks.Application` 都不能運作。後果：帶有 `OUT` 參數或 COM 介面參數的 API 方法（例如 `SelectByID2` 的 `Callout`、`AddSpecificDimension` 的 `Error`）無法到達。每個新的 API 表面都需要 sandbox 確認。請見 [docs/known_gotchas.md](../../known_gotchas.md)。
- **SW state 是不可見的。** SW 狀態機（當前 sketch、目前選擇、編輯模式）住在 SW 的 UI 記憶體中；API 無法可靠地查詢它。每個操作都必須明確設定狀態。
- **`AddDimension2` 會開啟 Modify Dimension 彈窗**，在參數化模式下需要手動點擊。`swInputDimValOnCreate`（toggle 8）與 `swSketchEnableOnScreenNumericInput` 類別（toggle 78）的偏好設定在 SW 2024 SP1 上透過 pywin32 經驗證無法抑制它。記錄於 [spikes/phase0/MMP_DEBUG_SESSION.md](../../../spikes/phase0/MMP_DEBUG_SESSION.md)。**已提供解法：`ai-sw-build --no-dim`** 先在 Python 中對 `locals.txt` 解析 `{rhs}` 參考、以字面目標尺寸建構幾何、跳過每一個 `AddDimension2` 呼叫。權衡：產生的 SLDPRT 沒有連結到 `locals.txt` 的方程式（編輯 locals 需要重跑 `ai-sw-build`）。MMP `--no-dim` 約 3 秒內建出且 0 次手動點擊，相對於參數化模式約 60 秒 + 約 16 次點擊。

**效能與 AI 迭代**

- **COM 每次呼叫約 5-50ms。** 30 個特徵的零件需要約 200 次呼叫 = 30-120 秒端對端。AI 迭代必須是 *先規劃再執行*，而不是一次一個呼叫。

**v0.2 今日範疇**

- **沒有 fluent 零件建構 API。** 沒有 `part.box().hole()` 鏈式呼叫。v0.2 是 JSON-spec → direct-COM。AI 產生 spec JSON，不是自由散文。
- **有限的 face/edge 選擇。** SW 透過 3D 座標選擇 faces，而非「特徵 X 的外側 face」。Builder 從特徵幾何計算座標，並在中心因先前的特徵切除了材料而失敗時嘗試小幅偏移作為 fallback。在如同心孔等邊緣情況下脆弱。
- **沒有 fillets、sweeps、lofts。** 需要人類判斷（哪些 edges）或無法乾淨地對應到宣告式 spec 的路徑幾何。延後處理。
- **沒有 assemblies、沒有 mates、沒有 drawings。** 每個都是獨立的問題。目前的 bridge 只處理 part 層級的工作流。
- **沒有「用英文描述零件就能得到幾何」。** Spec 語言是精確的。AI 產生 spec JSON。
- **不會取代 CAD 工程師。** 這是讓設計者更有生產力、更可重現的工具。

## 快速開始

### 先決條件

- **Windows**（SOLIDWORKS 僅支援 Windows，且 `pywin32` 僅支援 Windows）
- **SOLIDWORKS** 已安裝並執行中（在 2024 SP1 上測試；應該也能在 2021 SP5+ 上運作）
- **Python 3.10+**（在 3.14 上測試）

### 安裝

```powershell
git clone https://github.com/Thomas-Tai/ai-sw-bridge.git
cd ai-sw-bridge

python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

安裝後，**五個** CLI 命令會出現在你的 PATH 上：

| 命令 | 用途 |
|---|---|
| `ai-sw-probe` | COM 連線健全性檢查 |
| `ai-sw-observe` | 唯讀檢視（特徵、方程式、配對、螢幕擷取） |
| `ai-sw-mutate` | 對 `*_locals.txt` 變數的 Propose–Approve–Execute 變更 |
| `ai-sw-codegen` | Path C：參數化錄製的 `.swp` 巨集 |
| `ai-sw-build` | **v0.2**：透過 direct-COM 從 JSON spec 建出零件 |

### 冒煙測試

開啟 SOLIDWORKS，然後：

```powershell
ai-sw-probe
```

你應該會看到：
```json
{
  "ok": true,
  "sw_revision": "32.1.0",
  "active_doc": null,
  "error": null
}
```

## 五分鐘導覽

### 1. 檢視模型（安全、唯讀）

```powershell
ai-sw-observe active_doc
ai-sw-observe feature_errors
ai-sw-observe equations
ai-sw-observe screenshot --width=1280 --height=720
ai-sw-observe mate_errors                              # 僅 assemblies
ai-sw-observe measure                                  # 使用當前 SW UI 的選擇
```

每個命令會印出一個 JSON 物件到 stdout。失敗時 exit code 非零。

### 2. 變更參數化變數（Propose–Approve–Execute）

你當前的 SOLIDWORKS 零件必須有連結的 `*_locals.txt` 方程式檔案：

```powershell
ai-sw-mutate propose --var=PART_DIAMETER --new_value=30.0
# -> { "proposal_id": "abc123def456", ... }

ai-sw-mutate dry_run --proposal_id=abc123def456     # 套用、rebuild、擷取、回滾
ai-sw-mutate commit  --proposal_id=abc123def456     # 僅在 dry_run_ok 後允許
ai-sw-mutate undo_last_commit
```

Proposals 以 JSON 形式持久化在 `./proposals/` 中，讓 AI 代理能跨工作階段繼續。

### 3. 從 JSON spec 建出零件（v0.2，direct-COM）

**預設使用 `--no-dim` 模式。** 它在數秒內建出且不需手動點擊。只在你特別需要對 `locals.txt` 的即時方程式連結時才用參數化模式（請見下方「兩種建構模式」）。

開啟 SOLIDWORKS（不需要先開一個 part —— builder 會建立一個新的），然後：

```powershell
# 最小的端對端範例：20×20×10 的盒子，其中一個 edge 帶 2mm fillet
ai-sw-build examples/filleted_box/spec.json --no-dim
```

預期輸出（約 3 秒）：

```json
{
  "ok": true,
  "features_built": ["SK_Box", "Extrude_Box", "Fillet_TopRightEdge"],
  "bindings_added": [],
  "save_as": null,
  "no_dim": true
}
```

另外三個可嘗試的範例，依複雜度排序：

```powershell
ai-sw-build examples/minimal_cylinder_v2/spec.json   --no-dim    # 2 個特徵
ai-sw-build examples/motor_mount_plate/spec.json     --no-dim    # 10 個特徵
ai-sw-build examples/tension_bracket/spec.json       --no-dim    # 8 個特徵、堆疊的 extrudes
```

Spec 是一個小型 JSON 檔案，依建構順序宣告特徵。長度是字面 mm 值（`20.0`）或綁定到 `*_locals.txt` 檔案中變數的表達式（`{"rhs": "\"PART_DIAMETER\""}`）：

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

Builder 會驗證 spec（schema + topological references + locals 檔案變數）、透過 `NewDocument` 建立新 part、依序走過特徵、並發出 direct-COM 呼叫。輸出為含有 `features_built` 與（在參數化模式中）`bindings_added` 的 JSON。

#### 兩種建構模式

| 模式 | 旗標 | 何時使用 | 權衡 |
|---|---|---|---|
| `--no-dim`（推薦） | `--no-dim` | 第一次測試。任何 spec 為真實來源的情境。Bridge 在每次編輯都重新執行的 AI 驅動工作流。 | 產生的 SLDPRT 沒有連結到 `locals.txt` 的方程式。之後編輯 locals 需要重跑 `ai-sw-build`。 |
| 參數化（預設） | *(無旗標)* | 當人類會在下游手動編輯 SLDPRT 並需要對 `locals.txt` 的即時連結時。 | 每次 `AddDimension2` 呼叫會開啟一個會阻塞的「Modify Dimension」彈窗，需要手動滑鼠點擊。MMP 大小的零件約 16 次點擊。在 SW 2024 SP1 上無法抑制；失敗的抑制嘗試鏈請見 [docs/known_limitations.md](known_limitations.md)。 |

在 `--no-dim` 模式中，每個 `{"rhs": "..."}` 參考都會先在 Python 中對 `spec['locals']` 解析，並在任何 SOLIDWORKS 呼叫之前替換為字面 mm 值。幾何會以正確的尺寸產出；SLDPRT 只是沒有方程式。

#### 撰寫你自己的 spec 之前

**請先讀 [docs/known_limitations.md](known_limitations.md)。** 三個尖銳邊緣會在人們第一次撰寫非範例零件時絆住他們：(1) face-sketch 原點是 part-origin 投影到 face 上的點，*而非* face 的中心；(2) 今天只有 extrudes 的 +/-z faces 能承載子 sketches；(3) 參數化模式的彈窗成本。三者都有記錄的解法，但都不是從第一次讀 schema 就能看出來的。

### 4. 手動錄製零件的參數化重播（Path C）

對於 v0.2 spec 語言還未涵蓋的形狀（fillets、sweeps、複雜輪廓），Path C 讓你能在 SW UI 中錄製一次並參數化重播：

```powershell
# 在 SW 中錄製零件（Tools → Macro → Record）。儲存為 recorded.swp。
# 寫一個小 spec，把錄製的 dims 對應到你的變數。
ai-sw-codegen parameterize examples/minimal_cylinder/recorded.swp examples/minimal_cylinder/spec.json
# 把產生的 .bas 貼到 VBE，按 F5。
```

請見 [examples/minimal_cylinder/README.md](../../../examples/minimal_cylinder/README.md)。

## API 參考（CHM 驗證過）

Bridge 為它呼叫的每個 SW API 保留一份權威參考，從 `sldworksapi.chm` 擷取：

- [docs/api_reference.md](../../api_reference.md) —— 可讀形式：簽章、參數文件、enum 值、可用性
- [docs/api_reference.json](../../api_reference.json) —— 機器可讀

### 支援的 SW API 表面

跨 7 個介面與 5 個 enums 的 24 個方法。每次呼叫的確切參數數量都會在執行階段被 [src/ai_sw_bridge/sw_types.py](../../../src/ai_sw_bridge/sw_types.py) 斷言 —— CHM 與我們呼叫之間的偏移會立刻失敗，並在錯誤訊息中附上期望的簽章。每個方法的完整參數列表在 [docs/api_reference.md](../../api_reference.md) 中。

**`ISldWorks`**（應用程式層級）

| 方法 | 參數 | 用途 |
|---|---|---|
| `NewDocument` | 4 | 從 template 建立新的 part/asm/drw |
| `GetUserPreferenceStringValue` | 1 | 讀取字串偏好（例如預設 template 路徑） |
| `GetUserPreferenceToggle` | 1 | 讀取 boolean 偏好 |
| `SetUserPreferenceToggle` | 2 | 寫入 boolean 偏好 |

**`IModelDoc2`**（文件層級）

| 方法 | 參數 | 用途 |
|---|---|---|
| `SelectByID` | 5 | 透過名稱 + 3D 座標選擇實體（舊版 5 參數形式；`SelectByID2` 的 Callout 參數在 late-binding 下無法到達） |
| `ClearSelection2` | 1 | 取消當前選擇 |
| `AddDimension2` | 3 | 在指引位置加入顯示尺寸 |
| `FeatureByPositionReverse` | 1 | 取得倒數第 N 個特徵（用於抓取剛建出的特徵以改名） |
| `EditRebuild3` | 0 | 僅 rebuild 當前 config 中過時的特徵（以屬性方式自動呼叫） |
| `EditUndo2` | 1 | Undo N 個動作 |
| `Parameter` | 1 | 取得命名的 dim 參數（`"D1@Sketch1"`）以供檢視 |
| `GetFeatureCount` | 0 | 計算 doc 中的特徵數（以屬性方式自動呼叫） |
| `SaveBMP` | 3 | 將當前 view 存成 BMP |

**`IModelDocExtension`**

| 方法 | 參數 | 用途 |
|---|---|---|
| `SelectByID2` | 9 | 文件中的 9 參數 select；`Callout` 介面參數透過 pywin32 late-binding 無法 marshal，所以我們改用舊版 `SelectByID` |

**`IFeatureManager`**

| 方法 | 參數 | 用途 |
|---|---|---|
| `FeatureExtrusion2` | 23 | Boss extrude（v0.2 中用於所有 boss/extrude 特徵） |
| `FeatureExtrusion3` | 23 | 較新的 extrude 變體（相同參數形狀；目前未使用） |
| `FeatureCut4` | 27 | Cut extrude（v0.2 中用於所有 cut 特徵）。**CHM 說 27 個參數** —— 缺少的 `AutoSelectComponents`、`PropagateFeatureToParts`、`OptimizeGeometry` 造成我們先前的 PARAMNOTOPTIONAL 失敗 |
| `CreateDefinition` | 1 | 建立每個特徵類型的資料物件（用於 SW 2020+ 標準 fillet 路徑；接受 `swFeatureNameID_e` int，例如 `swFmFillet=1`）。取代過時的單一呼叫形式用於 fillets/chamfers |
| `CreateFeature` | 1 | 消費一個填好的 feature-data 物件並建立特徵。資料 CDispatch 的 late-binding 傳遞已驗證可運作（Spike P） |

**`ISketchManager`**

| 方法 | 參數 | 用途 |
|---|---|---|
| `InsertSketch` | 1 | 在當前情境中開啟/關閉 sketch |
| `CreateCornerRectangle` | 6 | 以兩個對角建立矩形（v0.2 未使用 —— 無約束，dim 綁定時造成不對稱縮放） |
| `CreateCenterRectangle` | 6 | 以中心 + 角建立矩形。透過中心對角線固定，使 dim 縮放保持置中 |
| `CreateCircle` | 6 | 以中心點 + 圓周點建立圓 |

**`IEquationMgr`**

| 方法 | 參數 | 用途 |
|---|---|---|
| `Add2` | 3 | 加入一個方程式列（例如 `"D1@SK_Plate" = "S1B_W"`）。必須先執行 4 步連結序列（`FilePath` + `LinkToFile=True` + `AutomaticRebuild=True` + `UpdateValuesFromExternalEquationFile`） |

**`IFeature`**

| 方法 | 參數 | 用途 |
|---|---|---|
| `GetTypeName` | 0 | 區分「Boss」與「Cut」特徵（以屬性方式自動呼叫） |
| `GetNextFeature` | 0 | 走過特徵樹（以屬性方式自動呼叫） |

**Enums**（來自 `swconst.chm`，在 [`sw_types.py`](../../../src/ai_sw_bridge/sw_types.py) 中暴露為常數）

| Enum | 值 | 備註 |
|---|---|---|
| `swEndConditions_e` | 11 | `swEndCondBlind=0`、`swEndCondThroughAll=1`（不是 4 —— 4 是過時的 `swEndCondUpToSurface`）、`swEndCondMidPlane=6` 等 |
| `swStartConditions_e` | 4 | `swStartSketchPlane=0`（v0.2 所有 extrudes 的預設） |
| `swDocumentTypes_e` | 8 | Part=1、Assembly=2、Drawing=3 |
| `swDimensionType_e` | 17 | 用於 `AddSpecificDimension`（目前因 OUT 參數 marshalling 而無法到達） |
| `swSelectType_e` | — | 字串形式用作 `SelectByID` 的第 2 個參數（"PLANE"、"FACE"、"SKETCH"、"SKETCHSEGMENT"） |

**尚未接入 bridge**（但在 CHM 中可用，v0.3+ 的候選）：
`FeatureRevolve`、`FeatureChamferType`、`InsertCutSwept5`、`InsertProtrusionSwept`、`FeatureCutThin2`、`FeatureBossThin2`、`SimpleHole3`、`InsertMirrorFeature`、`InsertLinearPatternFeature`。把它們加到 [`tools/_api_extract_input.json`](../../../tools/_api_extract_input.json) 並重新產生以透過 `sw_types.py` 暴露。

固定半徑 fillets 已經接入（透過 CreateDefinition + ISimpleFilletFeatureData2 + CreateFeature 的 3 步管線加入，而非過時的 FeatureFillet3）。用法請見 [`examples/filleted_box/`](../../../examples/filleted_box/)。可變半徑 / 不對稱 / setback fillets 仍未接入（沒有立即的使用情境）。

由以下產生：

```powershell
# 1. 反編譯 CHM（一次性設定）
hh.exe -decompile spikes/phase0/_chm_decompiled "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\sldworksapi.chm"

# 2. 擷取在 tools/_api_extract_input.json 中宣告的方法 + enums
python tools/chm_extract.py batch tools/_api_extract_input.json docs/api_reference.json

# 3. 重新產生可讀 + Python stub 形式
python tools/gen_api_markdown.py docs/api_reference.json docs/api_reference.md
python tools/gen_sw_types.py docs/api_reference.json src/ai_sw_bridge/sw_types.py
```

產生的 [src/ai_sw_bridge/sw_types.py](../../../src/ai_sw_bridge/sw_types.py) 匯出 enum 常數（`SW_END_COND_THROUGH_ALL = 1` 等）與一個 `METHOD_SIGNATURES` dict。Builder 在每個 FeatureManager 呼叫之前呼叫 `assert_args()`，因此任何未來的參數數量偏移都會立刻失敗並附上清晰的診斷。

**教訓**：當 SW 呼叫返回 `PARAMNOTOPTIONAL` 或 `Invalid number of parameters` 時，第一件要檢查的事就是參數數量是否符合 CHM。（[commit c560e97](https://github.com/Thomas-Tai/ai-sw-bridge/commit/c560e97) —— `FeatureCut4` 是 27 個參數，不是我們先前傳的 24 個。）

## 今天你能建什麼

八個特徵原語，分三類。每個原語對所有長度欄位都支援字面 mm 值與 `{rhs}`-綁定的表達式，除非「parametric」欄位另有說明。

**Sketches**

| 原語 | 參考框架 | 參數化 | 限制 |
|---|---|---|---|
| `sketch_rectangle_on_plane` | Front / Top / Right 參考平面 | width、height、center | Center 預設 (0, 0) = part 原點 |
| `sketch_rectangle_on_face` | 較早 extrusion 的 +/-z face | width、height、center | 僅 +/-z faces；sketch 原點 = part-origin 投影到 face 上的點（不是 face 中心） |
| `sketch_circle_on_plane` | Front / Top / Right 參考平面 | diameter、center | Center 預設 (0, 0) = part 原點 |
| `sketch_circle_on_face` | 較早 extrusion 的 +/-z face | diameter | 僅 +/-z faces；圓心位置僅支援 mm（位置上不支援 rhs） |
| `sketch_circles_on_face` | 較早 extrusion 的 +/-z face | 每圓的 diameter | 相同的 face 限制；多圓 sketch，每圓一個 driving dim |

**Extrudes**

| 原語 | 軸繼承自 | 參數化 | 限制 |
|---|---|---|---|
| `boss_extrude_blind` | 父 sketch（plane 或 face） | depth | 僅 Blind end-condition |
| `cut_extrude_through_all` | 父 sketch | *(無 dim)* | Through-all end-condition |
| `cut_extrude_blind` | 父 sketch | depth | 僅 Blind end-condition |

**Modify**

| 原語 | 目標 | 參數化 | 限制 |
|---|---|---|---|
| `fillet_constant_radius` | 一個或多個透過 part-coord 點指定的 edges | radius | 僅固定半徑（無 variable / asymmetric / setback）；edge 透過點選擇，無「face 的所有 edges」的糖衣 |

每個原語的完整 schema 細節請見 [src/ai_sw_bridge/spec/schema.py](../../../src/ai_sw_bridge/spec/schema.py)。執行每個原語的實作範例請見 [examples/](../../../examples/)。

**已驗證於**：SOLIDWORKS 2024 SP1（rev 32.1.0）、Python 3.14、pywin32 late-binding。四個已交付的範例（cylinder、MMP、TensionBracket、filleted_box）在 `--no-dim` 模式下都能乾淨建出。

## Roadmap

三層，依缺少的能力多常阻擋真實硬體零件相對於加入成本來排序。

**近期（v0.3 —— 擴充現有功能）**

接下來的四個原語各自遵循 v0.2 中 `fillet_constant_radius` 的相同配方：先 spike `CreateDefinition` 管線，僅在失敗時回退到單一呼叫 API。每個原語約 45-60 分鐘。

- 子 sketches 的 `+/-x` 與 `+/-y` face 支援 —— 對 `_select_extrude_face` 的機械式擴充，無新 API
- `fillet_variable_radius`、`chamfer_constant_distance` —— 與固定半徑 fillet 同一 `CreateDefinition` 家族
- `simple_hole`（沉頭孔、沉孔）—— `IFeatureManager.HoleWizard5` 家族
- `linear_pattern`、`circular_pattern`、`mirror` —— 對現有特徵 pattern；把重複幾何摺成一個 spec entry

**中期（v0.4 —— 擴展零件詞彙）**

不同的 SW API 家族，各有其設計問題。每個都是多天的工作，不是幾分鐘。

- `revolve` —— 與 extrudes 不同的特徵家族；需要 profile sketch + 旋轉軸元素。用於 IdlerRoller、AxleEndCap、任何車削/旋削的零件。
- `sweep` 與 `loft` —— 路徑驅動；spec 語言需要能表達路徑幾何，不只是 profile。可能需要一個獨立的 `path_sketch` 特徵類型。
- 鈑金特徵 —— 基準法蘭、邊緣法蘭、sketched bend、flat pattern。整個獨立的 SW UI 模式。
- 參考幾何 —— 自訂參考平面、軸、點。任何不座落於 Front/Top/Right 上的 extrude 都需要。

**長期（「大部分的 SW API」）**

這些每一項都代表一個子系統而非單一特徵。只有在 v0.3-v0.4 詞彙穩定之後才現實。

- **Assemblies + mates** —— `IAssemblyDoc`、`IMate2`、元件放置。目前 bridge 能 *觀察* assemblies（mate_errors 工具）但不能建立它們。Propose–Approve–Execute 紀律可延續但 API 表面大致加倍。
- **Drawings** —— `IDrawingDoc`、view 放置、尺寸標註、BOM。與零件建構工作大致正交。
- **Surfaces** —— `IFeatureManager.InsertSurface*` 家族。主要用於 ID/造型工作，較少用於機械零件。
- **Configurations** —— 多變體零件含每個 config 的 dims。會觸及每個現有原語（每個都需要一個感知 config 的變體）。

**不在 roadmap 上**

- VBA 發射 —— 作為參數化模式彈窗抑制 fallback 進行調查；因 OLE compound-doc packaging 需求而有風險；請見 [docs/known_limitations.md](known_limitations.md)。若 SW 在此 build 上修好 `swInputDimValOnCreate` toggle 行為，可能重新考慮。
- Fluent Python builder API（`part.box().hole()...`）。JSON spec 是 AI 原生的撰寫表面；鏈式 API 在領域內已被拒絕十年，依架構審查所述。
- 從 pywin32 遷移到 comtypes/pythonnet。Late-binding 對使用中的 26 個方法中的 26 個都能運作。先前「cuts 無法到達」的結論是錯的（只是參數數量錯誤）；不要在錯誤的前提上重建基礎。

## 為什麼這樣設計

- **AI 代理需要可驗證、可逆的操作。** 每次變更都是 `propose → dry-run → review → commit`。回滾驗證會從磁碟讀回檔案並與快照比對。
- **`*_locals.txt` 檔案是真實單一來源。** 直接在 SW Equation Manager 中編輯變數是脆弱的（連結會覆寫它們）。我們永遠是編輯檔案，然後 reload + rebuild。
- **僅 late-binding pywin32。** `EnsureDispatch`/makepy 在大多數安裝上對 `SldWorks.Application` 都不能運作。我們接受 late-binding 的稅（一些 APIs 無法到達，請見 gotchas）並繞過它。
- **所有東西都用 JSON 進出。** 從任何 AI 代理 harness 都能輕易腳本化 —— Claude Code、OpenAI Assistants、自訂 MCP servers、純 shell scripts。
- **CHM 是權威的。** API 簽章會在 SW 版本之間改變。在乾淨的 SW 安裝上重新擷取；產生的 `sw_types.py` 會自動調整執行階段的參數數量斷言。

## 佈局

```
ai-sw-bridge/
├── src/ai_sw_bridge/
│   ├── sw_com.py            # SldWorks dispatch + helpers
│   ├── sw_types.py          # auto-generated enum constants + assert_args
│   ├── observe.py           # Phase 1: read-only tools
│   ├── mutate.py            # Phase 2: Propose-Approve-Execute
│   ├── locals_io.py         # *_locals.txt parser + atomic writer
│   ├── parameterize.py      # Path C: recorded-macro parameterizer
│   ├── spec/                # v0.2: JSON-spec build pipeline
│   │   ├── schema.py        # JSON schema for the spec language
│   │   ├── validator.py     # 3-layer validation (schema, refs, locals)
│   │   └── builder.py       # direct-COM build executor
│   └── cli/                 # CLI entry points
├── tools/
│   ├── chm_extract.py       # decompiled-CHM signature/enum parser
│   ├── gen_api_markdown.py  # JSON → docs/api_reference.md
│   ├── gen_sw_types.py      # JSON → src/ai_sw_bridge/sw_types.py
│   └── _api_extract_input.json  # which methods/enums to extract
├── docs/
│   ├── architecture.md                     # phases, design rationale (v0.1)
│   ├── ai_driven_architecture_review.md    # field survey + v0.2 plan
│   ├── tools_reference.md                  # every CLI command, every flag
│   ├── known_gotchas.md                    # things we learned the hard way
│   └── api_reference.{md,json}             # CHM-verified SW API reference
├── examples/
│   ├── minimal_cylinder/        # Path C example (recorded macro → parametric)
│   ├── minimal_cylinder_v2/     # v0.2 example (JSON spec → direct-COM)
│   └── motor_mount_plate/       # v0.2 spec for the S1b MMP (partial; v1 limitation)
├── spikes/phase0/                # Phase 0 de-risking spikes + MMP debug log
├── USAGE.md
├── CHANGELOG.md
├── pyproject.toml
└── requirements.txt
```

## License

MIT。請見 [LICENSE](../../../LICENSE)。

## Acknowledgments

SOLIDWORKS API patterns 參考：[CodeStack](https://www.codestack.net/solidworks-api/)。Path C 的 dim-binding 修正（`EquationMgr.Add2` 3 參數形式）來自他們的 `document/dimensions/add-equation/` 範例。
