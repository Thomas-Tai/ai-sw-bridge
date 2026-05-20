---
translated-from: c8ce816
---

# 已知限制

> **Language**: [English](../../known_limitations.md) · 繁體中文

在撰寫你的第一份規格之前，請先閱讀本文。每個章節說明一個坑、如何辨識你踩到了，以及替代方案。

關於程式碼庫擴充的注意事項（pywin32 封送處理、SW API 怪異行為），請參閱 [known_gotchas.md](../../known_gotchas.md)。

---

## 1. 面草圖原點 = 零件原點投影，不是面重心

「幾何出現在錯誤位置」臭蟲的最大來源。當你透過 `sketch_rectangle_on_face`、`sketch_circle_on_face` 或 `sketch_circles_on_face` 在先前擠出的面上繪製草圖時，**草圖區域原點位於零件原點投影到該面上的位置**，而不是面的幾何中心。

如果父擠出體以零件原點為中心（這正是 MMP 的做法 — 其底板是在 Front Plane 上穿過原點的 `CreateCenterRectangle`），兩者會重合。一旦父擠出體偏離原點，兩者就會分歧。

### 如何辨識

- 你預期子特徵在面上居中，但它卻出現在面的邊緣（或完全超出面，產生半切的孔或懸空的板）。
- `doc.GetPartBox(True)` 顯示的 Y 或 X 範圍是你預期的 2 倍。
- 視覺上：子方塊向下突出超出父體底面積剛好半個父體的相關尺寸。

### 實際範例（TensionBracket §13.3）

內側蓋板在規格中偏移，使其落在零件框架 Y ∈ [0, 15]：
```json
{"type": "sketch_rectangle_on_plane", "name": "SK_InboardCap",
 "plane": "Front", "width": 20, "height": 15,
 "center": {"x": 0.0, "y": 7.5}}
```

現在蓋板在零件框架 X/Y 中的重心是 `(0, 7.5)`，但零件原點在 `(0, 0)`。蓋板的 `+z` 面繼承了這一點：面幾何中心在零件 `(0, 7.5, 3)`，但面草圖原點落在零件 `(0, 0, 3)`。

蓋板頂部的槽板需要置中於蓋板的重心（Y=7.5），因此其規格必須偏移草圖：
```json
{"type": "sketch_rectangle_on_face", "name": "SK_SlotSlab",
 "of_feature": "Extrude_InboardCap", "face": "+z",
 "width": 8.5, "height": 15,
 "center": {"u": 0.0, "v": 7.5}}
```

如果沒有那個 `v: 7.5`，槽板會落在零件 Y ∈ [-7.5, 7.5] 而非 [0, 15]，邊界框會變成 Y 方向 22.5mm 而非 15mm。

### 替代方案

1. 在腦中追蹤你的父擠出體幾何中心在零件座標中的位置。
2. 如果不是 `(0, 0)`，在每個子面草圖中加入 `center: {u: <dx>, v: <dy>}` 欄位來補償。
3. 建構完成後，執行 `doc.GetPartBox(True)`（乘以 1000 得到 mm）並與你預期的尺寸比對。邊界框是最便宜的現實檢查。

### 執行時偵測

當建構器偵測到非原點對齊的父體上的面草圖，且你未指定 `center` 偏移時，會向 stderr 發出警告。警告包含父體的面中心座標，讓你可以判斷預設值是否是你想要的。

---

## 2. 只有擠出體的 `+/-z` 面可以承載子草圖

建構器中的 `_select_extrude_face` 目前只接了 `+z` 和 `-z`。如果你寫 `"face": "+x"` 或任何 `+/-y` 值，建構器會拋出 `NotImplementedError`。

### 如何辨識

```
RuntimeError: v1 only supports +z/-z (out/in board) faces of extrusions; got +x
```

### 替代方案

重新調整父擠出體的方向，使你想繪製草圖的面成為其 `+z` 或 `-z` 面。由於擠出會繼承父草圖參考平面的軸向，這通常意味著為基礎草圖選擇不同的參考平面：

- 需要在方塊的 +X 面上繪製草圖？在 **Right Plane**（YZ，法線 +X）而非 Front Plane 上繪製方塊草圖。這樣 +X 面就成為方塊在橋接器區域框架中的 `+z` 面。
- 需要側面和頂面都可存取？你需要將零件拆成兩個堆疊的擠出體，一個的 `+z` 是原始的 `+z`，另一個的 `+z` 是原始的 `+x` — 目前沒有簡潔的做法。

### 移除此限制需要什麼

機械層面：擴充 `_select_extrude_face` 以在擠出軸為 `+/-Y` 或 `+/-X` 時（目前只接了 `+/-Z`）計算切平面偏移，並擴充面草圖處理器中的 mirror-u 邏輯。估計：60-90 分鐘，包含規格測試。已追蹤於 [CHANGELOG](../../../CHANGELOG.md) 的「近期」層級。

---

## 3. 參數化模式會觸發阻擋式 AddDimension2 彈窗

當你執行 `ai-sw-build` 時**不**加 `--no-dim`，每個有標註尺寸的草圖實體都會觸發一個「Modify Dimension」彈窗，需要手動按一下才能繼續建構。在 SW 2024 SP1 上，一個 MMP 規模的零件大約有 16 個彈窗。相關的 `swInputDimValOnCreate` 使用者偏好（切換 ID 8）讀回的值是預期的 `False`，但實際上並未抑制彈窗。

### 如何辨識

`ai-sw-build` 看起來像卡住了。SOLIDWORKS 顯示一個小型浮動的「Modify」對話方塊，帶有數值欄位和綠色/紅色勾選。CLI 正在等你逐一按過每一個。

### 替代方案

**使用 `--no-dim` 模式**，除非你特別需要在產生的 SLDPRT 中有到 `locals.txt` 的即時方程式連結：

```powershell
ai-sw-build my_spec.json --no-dim
```

在 `--no-dim` 模式下，建構器會在 Python 中預先將每個 `{"rhs": "..."}` 參考解析對應到 `spec['locals']`，替換為字面 mm 值，並跳過每個 `AddDimension2` 呼叫。幾何結果正確；SLDPRT 只是沒有連回 locals 的方程式。

### 為什麼這個問題尚未修復

三種失敗的抑制方法記載於 [spikes/phase0/MMP_DEBUG_SESSION.md](../../../spikes/phase0/MMP_DEBUG_SESSION.md) 以及 Spike M / Spike O 掃描中：

- `SetUserPreferenceToggle(swInputDimValOnCreate=8, False)` — 切換讀回值為已設定，彈窗仍然出現
- `SetUserPreferenceToggle(78, False)`（swSketchEnableOnScreenNumericInput 類別）— 同樣：無效
- `SendKeys("{ENTER}")` 關閉對話方塊 — 無法路由到強制回應子視窗
- `keybd_event(VK_RETURN)` 透過 Win32 — 可以關閉浮動彈窗，但 PM 窗格仍阻擋
- 完全繞過 AddDimension2，改用可查詢的內部 SW 尺寸（Spike O）— SW 不會自動建立可連結的尺寸物件

論壇上公認的建議（設定切換 8）據報在 SW 自身的 VBA 編輯器中有效，但不會傳播到此版本上的外部 pywin32 COM 用戶端。VBA 巨集回退方案（輸出 `.bas`，透過 `RunMacro2` 執行）是唯一剩餘的途徑，但也有其自身的風險；參見 [CHANGELOG "Not on the roadmap"](../../../CHANGELOG.md)。

### 第二個替代方案：`--deferred-dim`

`--deferred-dim` 為你提供即時方程式連結，但彈窗按鈕是**每個草圖時間局部化**的（單一草圖的所有彈窗連續出現，中間沒有 COM 呼叫延遲），而非交錯分散在多分鐘的幾何階段中：

```powershell
ai-sw-build my_spec.json --deferred-dim
```

在此模式下，幾何以佔位尺寸建構，不呼叫 `AddDimension2`；在每個草圖處理器回傳後，橋接器立即透過 `EditSketch` 重新進入草圖，在一個工作階段中重播所有 `AddDimension2` 呼叫，然後套用特徵的 `EquationMgr.Add2` 連結並重建。

**每個尺寸仍需按一次彈窗按鈕。** 每個 `AddDimension2` 呼叫仍會因一個手動「Modify Dimension」彈窗而阻擋。彈窗總數與**預設行內模式相同** — 每個有尺寸的實體一個按鈕。使用者可感知的改善是*時機*，而非*數量*：

- 行內模式：彈窗 → 數秒 COM 呼叫 → 彈窗 → 數秒 COM 呼叫 → ...（彈窗散布在整個建構過程中）
- `--deferred-dim`：僅 COM 的幾何建構（無彈窗）→ 草圖 A 的 N 個連續彈窗 → 草圖 B 的僅 COM 建構 → 草圖 B 的 M 個連續彈窗 → ...

你仍然按相同數量的彈窗。它們只是以可預測的叢集到達，中間穿插僅 COM 的建構階段。

如果你需要零彈窗，請使用 `--no-dim`（無方程式連結）。不存在同時提供即時連結和零彈窗的第四種模式 — 在測試了 12 種候選抑制路徑後已經實證否定（參見 [deferred_dim_investigation.md](../../deferred_dim_investigation.md)）。

**矩形支援（已於 2026-05-20 修復，Spike ZF）：** 矩形草圖（`sketch_rectangle_on_plane`、`sketch_rectangle_on_face`）先前在 SW 2024 SP1 上的第二個邊尺寸會被降級為從動 (driven)，破壞了該尺寸的方程式連結。根本原因：API 端的 `CreateCenterRectangle` 會加入一個 UI 繪製等價物中不存在的多餘 Midpoint 關係，將 2-DOF 坍縮為 1-DOF。修復是 [`builder.py`](../../../src/ai_sw_bridge/spec/builder.py) 中的 `_strip_centerrectangle_midpoint_relation()`，從兩個矩形處理器在 `CreateCenterRectangle()` 之後立即呼叫。矩形規格現在在三種模式（預設行內、`--deferred-dim`、`--no-dim`）下都能提供完整的方程式連結。已在 `motor_mount_plate` 端對端驗證，D1 和 D2 都正確驅動其 `S1B_MMP_H`/`S1B_MMP_W` 連結。

Spike 軌跡 Z1–ZF（2026-05-19 至 2026-05-20）探索了 11 條緩解路線，最終 ZF 透過使用者 UI 檢查找到了根本原因。以下路線無效並記錄供歷史參考：逐草圖尺寸分組、建構對角線刪除、`IDisplayDimension.DrivenState` 覆寫（透過 pywin32 及透過 VBA 注入器 — 兩者皆不可達）、編輯中 `EditRebuild3`、手動 `CornerRectangle` + Midpoint、`gencache.EnsureModule` 依明確 GUID、`MakeSelectedDriving`、`LinkValue` 屬性、`Add3` 搭配 `swAllConfiguration`、`SetEquationAndConfigurationOption`、行內尺寸搭配延遲連結。

---

## 4. 邊選擇使用字面零件座標

圓角（`fillet_constant_radius`）及任何未來的邊目標基本操作透過邊上的 3D 點來選擇邊：

```json
{"type": "fillet_constant_radius", "name": "F", "radius": 2.0,
 "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}]}
```

這是機械性且可預測的，但這意味著**改變上游尺寸（例如方盒寬度）可能使邊移到其他位置，而字面邊點將不再命中它。**

### 如何辨識

`RuntimeError: could not select edge #0 at part (X, Y, Z) mm -- point not on any edge of current geometry`

### 替代方案

當你改變影響邊位置的尺寸時，更新規格中的字面邊座標以匹配。目前尚無「依索引取特徵 X 的邊」的定址方式。

未來的 `edges_by_face: "+z"` 語法糖（圓角化一個面的所有邊）可以處理常見情況而無需逐邊座標；已在路線圖上但尚未實作。

---

## 5. 每次執行 `ai-sw-build` 都會建立新的未命名 Part

建構器一律呼叫 `NewDocument`。它不會修改目前作用中的 SOLIDWORKS 文件。建構完成後：

- 出現一個新的「PartN」視窗（N 會自動遞增）。
- 先前作用中的視窗保持不變。
- 新視窗可能不是最上層的可見視窗（焦點取決於使用者點擊了什麼）。
- 如果你需要將 SLDPRT 存到磁碟，傳入 `--save-as <絕對路徑>`。否則零件只存在記憶體中，關閉 SW（或其視窗）時即會丟失。

這是刻意的 — 建構是可重現的，不會冒覆蓋手動編輯工作的風險。但這確實意味著在建構後立即執行 ai-sw-observe `screenshot` 呼叫時，如果其他視窗目前有焦點，可能不會顯示剛建構的零件。使用 `doc.GetTitle` 確認你正在檢查哪個文件；或遍歷 `sw.GetFirstDocument` 列舉所有開啟的文件。

---

## 6. Schema 驗證不會捕捉幾何不可能的情況

驗證器檢查：schema 形狀、特徵之間的拓撲參考、locals 檔變數是否存在。它不檢查：

- 面上的圓是否實際落在材料上（它可能完全位於先前切除的空隙中）。
- 圓角半徑是否大於最小相鄰邊。
- 產生的幾何是否封閉、有效或合理。

這些失敗在建構過程中以執行時例外呈現（`FeatureCut4 returned None`，或更糟，一個靜默成功但幾何損壞的建構）。建構後的邊界框完整性檢查是捕捉後者最便宜的方式。

---

## 回報新發現的坑

如果你遇到了可重現且不在本清單中的問題，請開一個 issue，附上：規格 JSON、完整的 CLI 輸出（包含追蹤資訊）、SW 版本（Help → About → 修訂字串），以及（部分）建構後的 `doc.GetPartBox(True)` 輸出。
