---
translated-from: c8ce816
---

# 為什麼 `--no-dim` 存在：AddDimension2 彈窗事後剖析

> **Language**: [English](../../why_no_addim2.md) · 繁體中文

> 目標讀者：未來的工程師（人類或 AI），那些忍不住想「修好」
> AddDimension2 彈窗阻擋器的人。本文記錄了我們嘗試了什麼、什麼
> 失敗了、以及為什麼，讓你不用重走同樣的死路。

## TL;DR

`IModelDoc2.AddDimension2` 會開啟一個 Modify-Dimension 彈窗，在 SW 2024 SP1 上**無法透過 pywin32 抑制**。我們交付了 `ai-sw-build --no-dim`，它會在 Python 中預先將 `{"rhs": "..."}` 參考解析對應到 `spec['locals']`，並跳過每個 `AddDimension2` 呼叫。取捨：產生的 SLDPRT 沒有到 `locals.txt` 的即時方程式連結（重新執行 `ai-sw-build` 以傳播編輯）。

**如果你是因為有人告訴你「只要把 `swInputDimValOnCreate` 設為 False」而來 — 請繼續讀。我們試過了。三次。在此版本上從外部 COM 用戶端是無效的。**

## 問題

`AddDimension2(x, y, z)` 是 SW 將數值綁定到草圖尺寸的方式，讓 `EquationMgr.Add2` 之後可以依名稱（例如 `"D1@SK_Body"`）鎖定。在 SW 2024 SP1 上，每次呼叫會開啟**兩個**對話方塊：

1. 一個小型浮動的 **Modify Dimension 彈窗**（數值 + 綠色/紅色勾選）
2. 左側的 **Dimension PropertyManager (PM) 窗格**（綠色/紅色勾選）

兩者都必須關閉後 `AddDimension2` 才會回傳。此呼叫同步阻擋 — COM 執行緒停住直到使用者點擊。實測約**每個尺寸 ~12 秒**的人力注意。對於 MMP（約 15 個尺寸），每次建構約 ~30 次點擊。

## 我們嘗試了什麼以及每種方法失敗的原因

| 方法 | Spike | 結果 | 失敗原因 |
|---|---|---|---|
| 切換 8（`swInputDimValOnCreate`）`SetUserPreferenceToggle(8, False)` | [spike_i_verify_toggle.py](../../../spikes/phase0/spike_i_verify_toggle.py) | 失敗 | `GetUserPreferenceToggle(8)` 在 Set 呼叫前後都讀回 False，但 `AddDimension2` 仍阻擋 ~12 秒。可能是 ID 8 在此版本上不是 `swInputDimValOnCreate`，或者該偏好根本不從外部 COM 上下文管控 `AddDimension2`。 |
| 切換 78（`swSketchEnableOnScreenNumericInput` 類別，論壇建議為「真正的」切換） | [spike_m_toggle_78.py](../../../spikes/phase0/spike_m_toggle_78.py) | 失敗 | 結果與切換 8 相同。Pywin32 + SW 2024 SP1 兩者皆忽略。 |
| `keybd_event(VK_RETURN)` 盲注入 | [spike_h_sendkeys.py](../../../spikes/phase0/spike_h_sendkeys.py) | 部分有效 | 盲 keybd_event 確實能關閉 Modify 彈窗，但 PM 窗格仍保持焦點。雙重 ENTER（間隔 200ms）不可靠 — 第一個 ENTER 關閉彈窗後，焦點回到啟動終端機，第二個 ENTER 不會落在 SW 中。`sw.SendKeys("{ENTER}")` 和 keybd_event + `SetForegroundWindow` 都完全失敗（焦點從強制回應視窗被搶到主視窗）。 |
| `doc.Extension.RunCommand(1, "")` 關閉 PM 窗格 | [spike_f_close_pm.py](../../../spikes/phase0/spike_f_close_pm.py) | 失敗 | 回傳 True 但窗格仍然開啟。`doc.ClosePropertyManager()` 和 `doc.Extension.CloseAndDestroyPropertyManagers()` 都拋出 AttributeError（在此版本上不是成員）。 |
| `AddSpecificDimension`（AddDimension2 的型別替代方案） | [spike_j_specific_dim.py](../../../spikes/phase0/spike_j_specific_dim.py) | 失敗 | 全部 9 個 `DimType` 值（1-9）回傳 `com_error('Type mismatch.', ..., 5)`，每個約 0.1 秒。OUT `Error` 參數無法透過 pywin32 晚期繫結綁定 — 與 `SelectByID2` 的 `Callout` 參數同類失敗（參見 [known_gotchas.md](../../known_gotchas.md)）。此方法在此用戶端上無法使用。 |
| 查詢內部 `D1`/`D2`/`Diameter@...` 尺寸參數**而不**呼叫 AddDimension2 | [spike_o_param_without_dim.py](../../../spikes/phase0/spike_o_param_without_dim.py) | 失敗 | 對 `--no-dim` 圓柱探測了 9 個候選名稱。全部 9 個回傳 None。SW 不會自動在草圖/特徵上建立可查詢的尺寸參數；透過 `EquationMgr.Add2` 的可連結性需要一個具名尺寸，而這需要 AddDimension2。 |

附註：SW 2024 SP1 主視窗類別不是 `"SldWorks"` — 而是 `Afx:*` 類別。標題前綴 `"SOLIDWORKS"` 可用於 `FindWindow`。記錄於此，以防下次嘗試基於焦點的替代方案時需要用到。

## 為什麼社群建議不適用

至少有三個獨立的社群公認建議（angelsix/codestack/論壇）指向 `swInputDimValOnCreate`（切換 8）作為 Modify-Dim 彈窗的修復方案。它們有效 — 但**僅在 SW 的 VBA 編輯器內部**，在那裡切換值在同一個處理程序 / COM 上下文中與尺寸建立一起生效。從 SW 2024 SP1 上的**外部 pywin32 COM 用戶端**，切換 8 和切換 78 都無效。Spike I 和 M 獨立確認了這一點。

這是我們部署上下文（外部 Python 處理程序透過晚期繫結 COM 驅動 SW）特有的病理情況，不是 API 的誤用。

## 我們改為交付了什麼：`--no-dim`

當設定 `ai-sw-build --no-dim` 時，規格中的每個 `{"rhs": "..."}` 參考會在**任何 SW 呼叫之前**於 Python 中解析對應到 `spec['locals']`。字面 mm 值替換到規格中，幾何以字面目標尺寸建構，每個 `AddDimension2` 呼叫以及整個 `EquationMgr.Add2` 連結階段都被跳過。

實作：
- `_load_locals_map`、`_eval_rhs`、`_resolve_rhs_in_spec` 在
  [src/ai_sw_bridge/spec/builder.py](../../../src/ai_sw_bridge/spec/builder.py)
 （第 117-203 行）。處理帶引號的變數參考（`"VAR"`）、算術運算和遞迴 locals（一個變數參考另一個）。循環會拋出例外；未知參考會拋出 KeyError。
- `BuildContext` 新增了 `no_dim: bool` 欄位；每個特徵處理器在其 `AddDimension2` 區塊上用 `if not ctx.no_dim` 做條件判斷。
  幾何建立路徑不變。
- CLI 旗標接線在 [src/ai_sw_bridge/cli/build.py](../../../src/ai_sw_bridge/cli/build.py)。

在 SW 2024 SP1 上的驗證：
- 圓柱 `--no-dim`：**1.72 秒，0 次點擊**，Ø25 × 80mm 驗證通過
- MMP `--no-dim`：**~3 秒，0 次點擊，10/10 特徵**，截圖驗證通過
  （參數化模式約 ~60 秒 + ~16 次點擊）

**取捨**：產生的 SLDPRT 沒有到 `locals.txt` 的方程式連結。
編輯 `locals.txt` 不會傳播到現有零件；使用者必須重新執行 `ai-sw-build`。locals 檔仍然是唯一的真相來源 — 只是在建構時解析而非執行時。

## 尚未探索的路徑

未來的工程師可能會走的路：

- **VBA 巨集回退方案。** 每次建構輸出一個 `.bas`，然後透過 `RunMacro2` 從 SW 的 VBA 上下文內部叫用它，切換 8 在那裡可能實際有效。估計成本：~1-2 小時，包含 `.swp` 封裝調查（`RunMacro2` 不能直接使用純文字 `.bas` — 參見 [../CHANGELOG.md](../../../CHANGELOG.md) 中的 v0.1 已知限制）。這恢復了完整的可連結性。參見 [[project_sw_bridge_next]] Direction B'（引用自專案記憶；不在本儲存庫中）。

- **切換 ID 探測掃描。** 已撰寫但未執行
  [spike_n_toggle_discovery.py](../../../spikes/phase0/spike_n_toggle_discovery.py)。
  將暴力探測 4 個候選切換 ID（8、78、95、167），搭配新文件循環。跳過是因為 Spike I + M 共同表明切換方法在 pywin32 層**無論哪個 ID 是「正確的」**都已死路。可能結果：更多無效切換。

- **不同的 SW 版本。** SW 2025+ 可能有不同行為 — Anthropic 尚未在其他版本上重現此問題。未測試。

## 如果你忍不住想再試一次切換 8

別試。

我們有**三個** spike 產物證明它在此版本上無效（[spike_i_verify_toggle.py](../../../spikes/phase0/spike_i_verify_toggle.py)、
[spike_m_toggle_78.py](../../../spikes/phase0/spike_m_toggle_78.py)、
[spike_o_param_without_dim.py](../../../spikes/phase0/spike_o_param_without_dim.py)）。
切換讀回值是你設定的值，但 `AddDimension2` 仍阻擋 ~12 秒等待手動點擊。

正確的前進路線是：
- **`--no-dim`** 用於 AI 驅動的建構（不需要即時可連結性）
- **VBA 巨集回退方案** 用於確實需要到 `locals.txt` 的即時方程式連結的罕見情況

如果你必須重新調查，請先完整閱讀
[../spikes/phase0/MMP_DEBUG_SESSION.md](../../../spikes/phase0/MMP_DEBUG_SESSION.md)
— 上面的每條死路都可以從 [../spikes/phase0/](../../../spikes/phase0/) 中的 spike 腳本重現。
