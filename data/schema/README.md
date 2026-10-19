# 資料契約 v1

網站只讀這份格式的 JSON。換題目時只換 JSON，不改網站程式。

- 契約：[`topic.schema.json`](topic.schema.json)（JSON Schema 2020-12，每個欄位都有中文說明）
- 驗證：`python3 data/schema/validate.py data/mock/*.json`（需要 `pip install jsonschema`）
- 狀態：資料已確認（2026-10-19），待網站工程師確認。定版後只能新增欄位，不改名、不刪欄位；要改須兩人同意。

## 檔案與網址

一個題目一個檔案，檔名就是題目 id，網站用 `?topic=<id>` 載入 `data/mock/<id>.json`。

```
{
  "meta":       {…},   基本資訊        所有頁面的頁首與頁尾
  "heatmap":    {…},   熱力圖          Main
  "kpis":       […],   重點數字 3 張   Main 上方
  "decide":     {…},   幫你決定        V2Setup、V2Today、A*App
  "collective": {…},   如果大家都這樣  V2Today
  "scenario":   {…},   錯峰情境        Scenario
  "city":       {…},   城市行動        V2City、A*City
  "brief":      {…}    協商一頁紙      V2Brief
}
```

8 個區塊都必填。某題用不到的區塊（例如非交通題沒有排隊模型）仍要放最小內容，網站依內容決定要不要顯示，避免讀不到欄位就整頁壞掉。

## 兩條硬規則

**1. 每個數字都帶 `label` 與 `sim`。** 契約裡只有兩種「數字」寫法，都強制這兩個欄位：

| 寫法 | 用在哪裡 | 例子 |
| --- | --- | --- |
| `num`：單一值或區間 | 所有單一數字（分鐘、名額、人數、容量…） | `{"value": 12, "unit": "分", "label": "computed", "sim": true}`<br>`{"value": 9, "lo": 4, "hi": 13, "unit": "% 改時段", "label": "computed", "sim": true}`<br>還沒有數字：`{"pending": true, "label": "observed", "sim": true}`（網站顯示「待補」） |
| `cell`：格子或曲線上的點 | 熱力格、副圖、曲線、一頁紙色帶 | `{"v": 23, "label": "observed", "sim": false}`<br>沒有資料：`{"gap": true}`（不補值） |

`label` 只能是 `observed`（真實觀測）、`computed`（程式計算）、`assumed`（情境假設）、`ai`（AI 生成）。`sim: true` 的數字網站要加斜線紋路。缺 `label` 或 `sim` 就是契約錯誤，網站顯示錯誤，不預設成真實。

例外有三處，因為數字成組出現或寫在句子裡，標示放在所屬的最小物件上：
- `kpis[]` 每張卡本身帶 `label`、`sim`（值可以是字串，如 `"08:30–09:15"`）。
- `scenario.baseline` 與 `scenario.results[]` 每組帶一個 `label`、`sim`，組內的曲線陣列是純數字。
- `brief.conclusion` 的數字寫在句子裡，整句帶一個 `label`、`sim`。

`meta.sim` 為 `true`（模擬檔）時，檔內所有 `sim` 都必須是 `true`，且要填 `meta.mock_method` 寫明模擬方法。

**2. 網站不即時計算。** 情境結果、省下的分鐘、剩餘名額都由資料或排隊模型預先算好放進 JSON。網站只做三件事：依門檻上色、依使用者設定挑一份資料、篩掉不符合彈性的選項。

## 各區塊重點

### `meta`
題目名稱、地區、`time_range`、`bin_minutes`（時間格長度）、`sources`（所有資料來源，其他地方用 `src` 參照其 id）、`updated_at`、`sim`、`mock_method`、頁尾 `disclaimer`。

### `heatmap`
- `rows`：地點，帶 `kind`（`observed`／`sim`／`gap`，決定列首標籤）與示意圖座標 `x`、`y`（0–100）。
- `cols`：時段，`id` 用英數（如 `t0815`），`label` 是顯示文字。
- `layers`：每個圖層（車速、流量…）各自帶 `cells`（rows × cols 二維陣列）、`unit`、`direction`（`low_is_bad` 或 `high_is_bad`）、5 個 `thresholds` 切出 6 級色階、圖例文字，以及選填的 `level_text`（選取格子時的一句話）。
- 色碼不寫在 JSON 裡：網站用色階等級 0–5 對到 `tokens.css` 的變數。
- `aux`：矩陣旁的副圖（#4 是文湖線負載），依 `cols` 排列。
- 多天資料：格子可加 `lo`、`hi`（各天最小、最大）、`days`（天數）、`bad_days`（達到圖層 `bad_at` 的天數），`days_label` 寫明是哪幾天。網站用來顯示「4 天裡有 3 天會塞」，不只顯示平均。

### `kpis`
剛好 3 張：`title`、`value`、`unit`、`note`、`label`、`sim`，選填 `ref` 指到矩陣上的格子。

### `decide`
- `metric`：比較用的代價，#4 是「路上時間（分）」，停車題換成「步行（分）」。
- `setup`：設定畫面的選項，`rows`（可選的入口）、`deadlines`、`flex`（每個選項的 `allows`：`both`／`earlier`／`later`／`none`）、`origins`（設定第一步「從哪裡出發」，各自列出對應的入口；`rows` 為空代表目前無法給建議）、`constraints`（「為什麼沒辦法錯峰」，可複選，連到 `city.actions`，並附分享卡用的句子）。
- `plans`：每個「入口 × 最晚到達」一份，內含 `options`、`recommended`、`baseline`、`reason`。每個選項有 `key`（經過入口的時間或地點名；交通題不寫出門時間，因為不知道使用者從哪裡出發）、`arrive`、`cost`、`saved`（與基準相比，已算好，個人分鐘數一律給區間）、`arrive_early`（比平常早幾分鐘到，和 `saved` 一起顯示）、`slot_left`、`status`（`open`／`full`／`peak`／`late`）。

### `collective`
- `modes`：剛好 3 種，`solo`（只有你）、`same`（大家照同一建議）、`split`（依名額分散），各帶 `delta`、一句話、`curve`（依 `cols`）與要框起來的 `highlight` 時段。
- `claims`：各時段認領分布。名額比例（`slots`）可以是情境假設；人數（`total`）一律 `pending`。

### `scenario`
- `slider`（`min`、`max`、`step`、`default`）、`references`（參考線，如檀香山 6–7%）、`peak_cols`、`targets`（提早／延後）、`capacity`（含上下限）。
- `baseline` 是移出 0% 的現況；`results` 每個 target × 每個滑桿刻度一筆，含 `queue_max`（區間）、`clear_time`、`delay_change`、`new_peak`、累積到達／通過曲線、每格排隊與前後差。驗證會檢查是否每個刻度都有。

### `city`
`goal`（一句話加需要移出的比例區間，由排隊模型反推，不換算成人數）、`claimed`（意向登記人數，一律 `pending`，網站沒拿到後端數字時顯示「尚無資料」）、`claimed_since`（起算日期）、`claimed_caption`（固定說明，如「意向登記，未經驗證」）、`actions`（標題、負責局處、為什麼、對你、成本文字、「我也需要」人數；需要跨縣市或跨機關協調的標 `cross_agency: true`）、`breakdowns`（設定答案的彙總，如大家從哪裡來、為什麼沒辦法錯峰，人數一律 `pending`）、`disclaimer`。

### `brief`
`exposure`（入口占比與色帶）、`conclusion`（一句話結論，整句帶標示）、`options`（做法比較）、`support`（市府配合）、`pilot`（試辦設計）、`public`（民意數字）、`sources_text`。

### `share`（選填）
分享卡。`places`（「我卡在哪裡」的選項，有 `row` 的對到熱力圖，沒有的是資料範圍外的地點）、`templates`（卡片文字，`{place}` `{time}` `{saved}` `{origin}` `{constraint}` 由網站代入，`needs` 要列出用到的欄位，驗證會檢查）、`sim_badge`（用到模擬數字時印在卡片上的文字）、`footer`。

## id 與參照

所有 id 用小寫英數、底線、連字號。驗證腳本會檢查以下參照都存在、數量對齊：

- `heatmap.layers[].cells` 是 rows × cols；`aux.values` 數量等於 cols。
- `decide.setup.rows`、`decide.plans[].row`、`brief.exposure.rows[].row` 都是 `heatmap.rows` 的 id；每個 `setup.rows` × `setup.deadlines` 都有一份 plan；`recommended`、`baseline` 是該 plan 的選項。
- `collective.cols`、`brief.exposure.cols` 是 `heatmap.cols` 的 id；曲線長度相符。
- `scenario` 的 `peak_cols`、`targets[].cols`、`new_peak` 是 `scenario.cols` 的 id；陣列長度等於 `scenario.cols`。
- 所有 `src` 都在 `meta.sources` 裡。

## 換題時

版面不變，只換內容：`heatmap.rows` 換成該題的地點（停車場、行政區、捷運站），`layers` 換成該題的指標（佔用率、陳情件數），`decide.metric` 換成該題的代價，`slot_left` 換成該題的容量（車位、班次載客量）。每個欄位的來源與計算方式記在 `data/FIELDS.md`。

## 已決定（2026-10-19）

1. `decide.plans` 依「入口 × 最晚到達」各一份（#4 為 4 × 4 = 16 份），時間彈性由網站篩選。
2. 8 個區塊都必填；題目用不到的區塊放最小內容。
3. 分享卡以選填區塊 `share` 加入（2026-10-19 新增，原本不放進 v1）。
4. 還沒有數字的項目寫 `{"pending": true}`，網站顯示「待補」，不刪掉項目。
5. 曲線與格子一律填實際數值（如 `collective.modes[].curve` 填車速），色階等級由網站依 `thresholds` 判斷，不在 JSON 裡填等級。
6. 人數（`city.claimed`、`collective.claims.total`、`city.actions[].support`、`city.breakdowns[]`、`brief.public[]` 中單位為「人」的值）不放模擬值，一律 `pending`，網站顯示「尚無資料」。驗證腳本會擋下 `sim: true` 的人數。（2026-10-19 追加）
