# 已知限制

> **Language**: [English](../../known_limitations.md) · Traditional Chinese (繁體中文)

撰寫你的第一個 spec 之前請先讀這份。每節指出一個尖銳邊緣、展示如何辨識你已撞上它、並提供解法。

關於程式碼擴充的陷阱（pywin32 marshalling、SW API 怪癖），請改見 [known_gotchas.md](../../known_gotchas.md)。

---

## 1. Face-sketch 原點 = part-origin 投影，**不是** face 中心

「幾何跑到錯誤位置」這類 bug 最大的單一來源。當你透過 `sketch_rectangle_on_face`、`sketch_circle_on_face` 或 `sketch_circles_on_face` 在較早 extrusion 的 face 上 sketch 時，**sketch local 原點是 part 原點投影到該 face 上的點**，不是 face 的幾何中心。

兩者會重合，前提是父 extrusion 以 part 原點為中心（這正是 MMP 在做的 —— 它的底板是 Front Plane 通過原點上的 `CreateCenterRectangle`）。一旦父 extrusion 偏離原點，兩者就會分歧。

### 如何辨識

- 你預期子特徵會以 face 為中心，但它卻落在 face 的邊緣（或完全在 face 之外，產生一個切了一半的孔，或一個懸空的板）。
- `doc.GetPartBox(True)` 顯示的 Y 或 X 範圍是你預期的 2 倍。
- 視覺上：子方塊在父 footprint 的下方剛好突出父相關尺寸的一半。

### 實作範例（TensionBracket §13.3）

Inboard cap 在 spec 中被位移到 part-frame Y ∈ [0, 15]：
```json
{"type": "sketch_rectangle_on_plane", "name": "SK_InboardCap",
 "plane": "Front", "width": 20, "height": 15,
 "center": {"x": 0.0, "y": 7.5}}
```

現在 cap 在 part-frame X/Y 的 centroid 是 `(0, 7.5)`，但 part 原點是 `(0, 0)`。Cap 的 `+z` face 繼承這點：face 幾何中心在 part `(0, 7.5, 3)`，但 face-sketch 原點落在 part `(0, 0, 3)`。

Cap 之上的 slot slab 需要以 cap 的 centroid（Y=7.5）為中心，因此它的 spec 必須對 sketch 加上偏移：
```json
{"type": "sketch_rectangle_on_face", "name": "SK_SlotSlab",
 "of_feature": "Extrude_InboardCap", "face": "+z",
 "width": 8.5, "height": 15,
 "center": {"u": 0.0, "v": 7.5}}
```

沒有那個 `v: 7.5`，slab 會落在 part Y ∈ [-7.5, 7.5] 而不是 [0, 15]，bounding box 在 Y 上會是 22.5mm 而不是 15mm。

### 解法

1. 心裡追蹤你的父 extrusion 幾何中心在 part 座標的位置。
2. 如果那不是 `(0, 0)`，對每個子 face-sketch 加上 `center: {u: <dx>, v: <dy>}` 欄位來補償。
3. 建構之後，執行 `doc.GetPartBox(True)`（乘以 1000 換成 mm）並與你預期的尺寸比對。Bounding box 是最便宜的事實檢查。

### 執行階段偵測

當 builder 偵測到一個 face-sketch 落在非原點對齊的父 extrusion 上、且你沒有指定 `center` 偏移時，會發出 stderr 警告。警告包含父的 face 中心座標，這樣你能看到預設是否就是你要的。

---

## 2. 只有 extrusions 的 `+/-z` faces 能承載子 sketches

Builder 中的 `_select_extrude_face` 目前只接好了 `+z` 與 `-z`。如果你寫 `"face": "+x"` 或任何 `+/-y` 值，builder 會 raise `NotImplementedError`。

### 如何辨識

```
RuntimeError: v1 only supports +z/-z (out/in board) faces of extrusions; got +x
```

### 解法

重新導向父 extrusion，讓你想 sketch 的 face 變成它的 `+z` 或 `-z` face。因為 extrudes 從父 sketch 的參考平面繼承軸，這通常代表為 base sketch 挑不同的參考平面：

- 需要在盒子的 +X face 上 sketch？把盒子 sketch 在 **Right Plane**（YZ、normal +X）而不是 Front Plane。然後 +X face 就在 bridge 的 local frame 中變成盒子的 `+z` face。
- 需要同時存取側 faces 與頂 face？你會需要把零件拆成兩個堆疊的 extrudes，一個的 `+z` 是原本的 `+z`、另一個的 `+z` 是原本的 `+x` —— 目前沒有乾淨的方法做到。

### 解除這個限制需要什麼

機械式：擴充 `_select_extrude_face` 在 extrude 軸是 `+/-Y` 或 `+/-X` 時計算切平面偏移（目前只接好 `+/-Z`），並擴充 face-sketch handlers 中的 mirror-u 邏輯。估計：含 spec 測試 60-90 分鐘。追蹤於 [Roadmap](README.md#roadmap)「near-term」層。

---

## 3. 參數化模式觸發會阻塞的 AddDimension2 彈窗

當你執行 `ai-sw-build` 而**沒有** `--no-dim` 時，每個有標註尺寸的 sketch 實體都會觸發一個「Modify Dimension」彈窗，需要手動滑鼠點擊才能讓 build 繼續。在 SW 2024 SP1 上，MMP 大小的零件約 16 個彈窗。相關的 `swInputDimValOnCreate` 使用者偏好（toggle ID 8）讀回是預期的 `False`，但經驗證**並不會**抑制彈窗。

### 如何辨識

`ai-sw-build` 看似卡住。SOLIDWORKS 顯示一個帶有數值欄位與綠/紅勾的小型浮動「Modify」對話框。CLI 在等你點過每一個。

### 解法

**使用 `--no-dim` 模式**，除非你特別需要產生的 SLDPRT 對 `locals.txt` 有即時方程式連結：

```powershell
ai-sw-build my_spec.json --no-dim
```

在 `--no-dim` 模式中，builder 先在 Python 中對 `spec['locals']` 解析每個 `{"rhs": "..."}` 參考、替換為字面 mm 值、跳過每個 `AddDimension2` 呼叫。幾何會正確產出；SLDPRT 只是沒有連回 locals 的方程式。

### 為什麼這沒有修

記錄於 [spikes/phase0/MMP_DEBUG_SESSION.md](../../../spikes/phase0/MMP_DEBUG_SESSION.md) 與 Spike M / Spike O 掃描中的三個失敗抑制方法：

- `SetUserPreferenceToggle(swInputDimValOnCreate=8, False)` —— toggle 讀回是已設定，彈窗仍然觸發
- `SetUserPreferenceToggle(78, False)`（swSketchEnableOnScreenNumericInput 類別）—— 一樣：無效果
- `SendKeys("{ENTER}")` 來消除對話框 —— 不會 route 到 modal 子視窗
- 透過 Win32 的 `keybd_event(VK_RETURN)` —— 消除浮動彈窗，但 PM pane 仍會阻塞
- 透過可查詢的內部 SW dims 完全繞過 AddDimension2（Spike O）—— SW 不會自動建立可連結的 dim 物件

論壇上的標準建議（設定 toggle 8）據報在 SW 自己的 VBA 編輯器內可運作，但在此 build 上不會傳遞到外部 pywin32 COM 客戶端。VBA-macro fallback（發射 `.bas`、透過 `RunMacro2` 執行）是唯一剩下的途徑，並帶有自己的風險；請見 [Roadmap「Not on the roadmap」](README.md#roadmap)。

---

## 4. Edge 選擇使用字面 part 座標

Fillet（`fillet_constant_radius`）與任何未來指向 edges 的原語透過 edge 上的 3D 點選擇 edges：

```json
{"type": "fillet_constant_radius", "name": "F", "radius": 2.0,
 "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}]}
```

這是機械式且可預測的，但代表**改變上游 dim（例如盒子寬度）會把 edge 移到別處，字面 edge-point 就不再命中它**。

### 如何辨識

`RuntimeError: could not select edge #0 at part (X, Y, Z) mm -- point not on any edge of current geometry`

### 解法

當你改變影響 edge 位置的 dim 時，更新 spec 中的字面 edge 座標來符合。目前還沒有「以索引指定特徵 X 的 edge」的定址方式。

未來的 `edges_by_face: "+z"` 糖衣（fillet 一個 face 的所有 edges）會處理常見情況、不需要每個 edge 的座標；在 roadmap 上但未實作。

---

## 5. 每次 `ai-sw-build` 都會建立一個新的未命名 Part

Builder 永遠呼叫 `NewDocument`。它**不會**修改當前活躍的 SOLIDWORKS 文件。Build 之後：

- 一個新的「PartN」視窗出現（N 自動遞增）。
- 先前活躍的視窗保持不變。
- 新視窗可能不是位於上層的可見視窗（焦點取決於使用者點了什麼）。
- 如果你要 SLDPRT 在磁碟上，傳 `--save-as <absolute_path>`。否則 part 只活在記憶體中，並在你關閉 SW（或它的視窗）時被丟棄。

這是有意的 —— builds 是可重現的、不會冒險覆寫手動編輯的工作。但這也代表 build 之後立刻呼叫 ai-sw-observe `screenshot` 可能不會顯示剛建好的 part，如果焦點目前在不同視窗上。用 `doc.GetTitle` 確認你正在檢視的是哪個 doc；或走 `sw.GetFirstDocument` 來列舉所有開啟的 docs。

---

## 6. Schema 驗證不會抓到幾何不可能性

Validator 會檢查：schema 形狀、特徵之間的拓樸參考、locals 檔案變數的存在。它**不會**檢查：

- face 上的圓是否真的會落在材料上（它可能完全坐在先前 cut 留下的空洞中）。
- fillet 半徑是否大於最小相鄰 edge。
- 產生的幾何是否封閉、有效、合理。

這些失敗會以執行階段例外的形式在 build 中浮現（`FeatureCut4 returned None`，或更糟：沉默成功的 build 帶著壞掉的幾何）。Build 之後的 bbox 健全性檢查是抓到後者最便宜的方法。

---

## 回報新的尖銳邊緣

如果你撞到可重現、且不在此清單中的東西，請開一個 issue，附上：spec JSON、完整 CLI 輸出（含 traceback）、SW build（Help → About → revision 字串）、與（部分）build 之後的 `doc.GetPartBox(True)` 輸出。
