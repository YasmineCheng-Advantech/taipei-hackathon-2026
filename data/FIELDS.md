# 欄位規劃表

Oct 22, 2026 · 固定版面上每個數字從哪裡來、怎麼算、標什麼、換題時要改什麼。格式見 [`schema/README.md`](schema/README.md)，產生方式見 [`mock/README.md`](mock/README.md)，換題步驟見 [`SOP.md`](SOP.md)。

**怎麼讀這份表**

- **欄位**：契約裡的路徑，`[]` 是陣列的每一項。表格涵蓋 `topic.schema.json` 裡所有數字欄位（`num`、`cell`、數字型別），共 54 個。
- **來源**：#4 正式版的數字從哪裡來。現在的 `t4-morning.json` 全部是模擬值，來源欄寫的是要換成什麼。
- **標籤**：`label` 填的值。`observed` 真實觀測、`computed` 程式計算、`assumed` 情境假設、`ai` AI 生成。
- **換題時**：版面不變，這格要換成新題目的什麼。例子用 A5 停車、A6 文湖線、B1 1999 陳情。
- 程式碼位置寫成 `gen_t4_morning.py` 的段落名稱（檔案裡的 `# ---------- … ----------`）。

**三條共通規則**

1. 人數（意向登記、「我也需要」、設定答案的彙總、民意數字裡單位為「人」的）一律 `pending`，不放模擬值。真實人數由網站後端給。
2. 有區間的數字（`lo`／`hi`）都要寫區間代表什麼：每天路況的差異，或容量估計的上下限。
3. `meta.sim` 為 `true` 時，所有 `sim` 都是 `true`。真實資料接進來的格子改 `sim: false`，`meta.sim` 跟著改 `false`。

## meta

| 欄位 | 來源 | 計算方式 | 標籤 | 換題時 |
| --- | --- | --- | --- | --- |
| `meta.bin_minutes` | 設定值 | 熱力圖一格的分鐘數，#4 是 15（VD 是 5 分鐘統計，3 筆併一格） | 不需要（設定值，不顯示成數字） | 時段題照資料粒度改（停車 15、捷運 60）；非時段題填 `1440`（見 `SOP.md`「容易出錯的地方」） |

## heatmap 熱力圖

| 欄位 | 來源 | 計算方式 | 標籤 | 換題時 |
| --- | --- | --- | --- | --- |
| `heatmap.rows[].x`、`.y` | 設計稿 `Main` 的入口示意圖 | 0–100 的示意座標，不是比例 | 不需要 | 換成新地點在示意圖上的位置；沒有示意圖時依經緯度等比例換算 |
| `heatmap.rows[].lat`、`.lng` | VD 靜態資料 `VD.xml` 的偵測器座標（`entrances.csv`） | 取對應偵測器的座標；缺口入口用地圖上的大略位置 | 不需要 | 換成停車場、捷運站、行政區中心的座標 |
| `heatmap.layers[].cells[][]`（車速） | 臺北市 VD 即時資料 `VDLive.xml` | `build_vd_15min.py`：每 15 分鐘，依車輛數加權平均車速；只用 `status = 0` 的讀數；多天另記 `lo`、`hi`、`days`、`bad_days` | 有偵測器的入口 `observed`；國 1 `observed`（待 TDX，目前模擬）；缺口 `{gap: true}` | 換成該題的主指標：停車「佔用率 %」、捷運「進站人次」、1999「每月件數」 |
| `heatmap.layers[].cells[][]`（流量） | 同上 | 每 15 分鐘的車輛數加總，不滿 3 筆時按比例補成 15 分鐘 | 同上 | 換成該題的第二指標，例如 1999 的「平均結案天數」；沒有就只放一個圖層 |
| `heatmap.layers[].thresholds[]` | 設計稿（車速 50/40/30/20/10 km/h、流量 400/600/800/1,000/1,200 輛） | 5 個門檻切出 6 級色階 | 不需要 | 依新指標的分布重設。建議取全部格子的 20/40/60/80 百分位，再取整數，並在 `legend` 寫出分界 |
| `heatmap.layers[].bad_at` | 設定值，車速 20 km/h | 低於這個值就算「塞」，用來數 `bad_days` | 不需要 | 換成「出問題」的定義：停車佔用率 ≥ 90%、捷運進站量超過月平均 1.5 倍 |
| `heatmap.landmarks[].x`、`.y` | 設計稿 | 示意圖上的地標位置（內科、基隆河） | 不需要 | 換成新題目的地標，或刪掉 |
| `heatmap.aux.values[]` | #4：文湖線負載（模擬）。正式版：北捷各站分時進出量（月檔，見 `catalog.md` A6） | 目前是 55 + 40 × 鐘形曲線；正式版用內湖各站每小時進出站量 ÷ 尖峰最大值，換算成 15 分鐘時要寫明假設 | 目前 `assumed`；換成北捷資料後 `observed` | 換成副指標，例如停車題放「周邊路邊停車格」；沒有就刪掉整個 `aux`（選填） |
| `heatmap.aux.alert_at` | 設定值，90% | 達到就加深顯示 | 不需要 | 依副指標重設 |

## kpis 重點數字（3 張）

| 欄位 | 來源 | 計算方式 | 標籤 | 換題時 |
| --- | --- | --- | --- | --- |
| `kpis[worst-cell].value` | 熱力圖車速 | 所有格子平均車速的最小值；有真實資料時只在真實格子裡挑；`note` 寫「N 天裡有 M 天低於 20 km/h」 | `computed` | 換成「最嚴重的一格」：佔用率最高、件數最多 |
| `kpis[peak-window].value` | 熱力圖車速 | 有偵測器的入口裡，半數以上低於 `bad_at` 的時段，第一格到最後一格 | `computed` | 時段題照用；非時段題換成「最多的類別」或「最慢的局處」 |
| `kpis[coverage].value` | `entrances.csv` | `kind = observed` 的列數 / 總列數 | `observed` | 換成「資料涵蓋幾個地點」，讓讀者知道多少格是真的 |

## decide 幫你決定

| 欄位 | 來源 | 計算方式 | 標籤 | 換題時 |
| --- | --- | --- | --- | --- |
| `decide.plans[].options[].cost` | VD 車速＋假設的自由車流分鐘 | 「幫你決定」段的 `travel()`：自由車流分鐘 × (1 + 壅塞係數 × 尖峰強度)；區間是壅塞係數 ±20%（每天路況不同）。正式版：入口到內科的路段長度 ÷ 該時段 VD 平均車速 | `computed` | 換成該題的代價：停車「步行分鐘」、捷運「等幾班車」、1999「預估回覆天數」 |
| `decide.plans[].options[].saved` | 由 `cost` 算 | 平常時段的 `cost` − 這個選項的 `cost`；區間取每天路況差異的最小與最大 | `assumed`（假設只有你改時間、其他人不變） | 同 `cost`，單位跟著換 |
| `decide.plans[].options[].arrive_early` | 由經過時間與 `cost` 算 | 平常到達時間 − 這個選項的到達時間（分）；正數早到、負數晚到 | `computed` | 時段題照用並改 `note` 的說法（晚尖峰是「早或晚經過出口」）；非時段題通常不需要，填 0 並在 `note` 說明 |
| `decide.plans[].options[].slot_left` | 情境假設（`SLOT_PCT`）；正式版由網站後端給 | 該時段的名額 − 已認領，換算成 %；名額 = `scenario` 算出不會形成新尖峰的移入量。尖峰時段不開放認領，省略這個欄位 | `assumed`（正式版容量估計仍是假設） | 換成該題的容量：車位數、班次載客量；沒有名額概念的題目（如 1999）省略 |

## collective 如果大家都這樣

| 欄位 | 來源 | 計算方式 | 標籤 | 換題時 |
| --- | --- | --- | --- | --- |
| `collective.modes[].delta` | 情境假設（照設計稿：−12、−2、−7 分） | 正式版：用 `scenario` 的排隊模型，分別算「只有你」「大家都移到同一格」「依名額分散」三種情況的平均每人延誤差 | `assumed`；改用模型算後 `computed` | 換成該題「大家都照建議」的後果：停車「大家都去同一個停車場會滿」、1999「大家都用 APP，APP 回覆變慢」 |
| `collective.modes[].curve[]` | 情境假設（色階等級對到代表車速 55/45/35/25/15/8） | 依 `cols` 排列的車速；正式版用模型算出的各格排隊換算車速 | `assumed` | 換成該題主指標在三種情況下的曲線 |
| `collective.claims.total` | 網站後端 | 意向登記人數 | 一律 `pending` | 不變 |
| `collective.claims.slots[].filled` | 情境假設；正式版由後端算 | 各時段已認領 ÷ 名額（%） | `assumed`；正式版 `observed`（但人數未經驗證） | `key` 換成該題的選項（管道、停車場），不一定是時間 |

## scenario 錯峰情境

模型輸入（容量、到達曲線）在 `inputs/model_input.json`（假設值）或 `processed/model_input.json`（由 `build_model_input.py` 從真實 VD 反推）。所有結果由 `gen_t4_morning.py` 的「情境」段預先算好，網站不計算。`sim` 跟著模型輸入走：輸入是假設值就是 `true`。

| 欄位 | 來源 | 計算方式 | 標籤 | 換題時 |
| --- | --- | --- | --- | --- |
| `scenario.slider.min`、`.max`、`.step`、`.default` | 設定值：0、50、5、5 | 滑桿刻度；`results` 每個刻度都要有一筆，驗證會檢查 | 不需要 | 依新題目調整範圍（停車可以到 100%） |
| `scenario.references[].value` | 檀香山 1988 錯峰試辦實際參與 6–7%（[Giuliano & Golob，1990](https://onlinepubs.trb.org/Onlinepubs/trr/1990/1280/1280-006.pdf)） | 取中間值 6.5 | 不需要（`text` 與 `src` 寫明出處） | 換成該題的國內外試辦或政策目標；找不到就刪掉 |
| `scenario.capacity` | VD `VPMSV40`（堤頂大道北向）塞車時段的最大通過量 | `build_model_input.py`：只算汽車；塞住的格子（車速低於平常車速的 40%）放行的汽車數取中位數，`lo`／`hi` 取四分位數；收集期間沒塞住時只知道容量的下限，改標 `assumed`。目前假設值 1,000 輛 ±10% | 假設值 `assumed`；由 VD 反推 `computed` | 換成瓶頸容量：停車場車位數、捷運班次載客量 × 班次、局處每週可結案件數 |
| `scenario.baseline.queue_max`、`results[].queue_max` | 排隊模型 | 每格 排隊 = max(0, 上一格排隊 + 到達 − 容量)，取最大值；`lo`／`hi` 用容量上下限各跑一次 | `computed` | 單位換成該題的「積壓」：等車位的車、月台上的人、未結案件 |
| `scenario.baseline.delay_change`、`results[].delay_change` | 排隊模型 | (情境的排隊總和 − 現況的排隊總和) ÷ 現況 × 100；現況為 0 | `computed` | 照用 |
| `scenario.*.cum_arrive[]`、`.cum_depart[]` | 排隊模型 | 累積到達、累積通過（= 累積到達 − 當格排隊） | 所屬 `result` 物件帶 `computed` | 照用 |
| `scenario.*.queue[]`、`.queue_diff[]` | 排隊模型 | 每格排隊；`queue_diff` = 情境 − 現況 | 同上 | 照用 |
| `scenario.results[].shift` | 滑桿刻度 | 尖峰時段移出的比例（%），平均移到 `targets` 的時段 | 同上 | 照用 |
| `scenario.sensitivity.base` | 排隊模型 | 「最長排隊減半要移出幾 %」，容量取中間值、沒有回流 | `computed` | 換成該題的核心結論（例如「積案減半要提前處理幾 %」） |
| `scenario.sensitivity.items[].low`、`.high` | 排隊模型 | 同上，但把一個假設調低或調高：容量上下限、尖峰高度 ±20%、尖峰寬度 ±20%、回流 30% | `computed` | 換成該題最不確定的假設 |
| `scenario.sensitivity.items[].spread` | 由 `low`、`high` 算 | \|high − low\|，由大到小排列 | 所屬物件帶 `computed` | 照用 |

## city 城市行動

| 欄位 | 來源 | 計算方式 | 標籤 | 換題時 |
| --- | --- | --- | --- | --- |
| `city.goal.need` | 排隊模型 | 同 `sensitivity.base`；`lo`／`hi` 對應容量上下限。`note` 換算成車輛數（尖峰總到達量 × 比例），不換算成人數 | `computed` | 換成該題「要做到多少才有感」 |
| `city.claimed` | 網站後端 | 意向登記人數 | 一律 `pending` | 不變 |
| `city.actions[].support` | 網站後端 | 「我也需要」人數 | 一律 `pending` | 不變；`actions` 的內容（局處、為什麼、對你）要換 |
| `city.breakdowns[].items[].count` | 網站後端 | 設定答案的彙總人數 | 一律 `pending` | `key` 跟著 `decide.setup.origins`、`constraints`、`rows` 換；自己取 id 的欄位要附 `label` |

## brief 協商一頁紙

| 欄位 | 來源 | 計算方式 | 標籤 | 換題時 |
| --- | --- | --- | --- | --- |
| `brief.exposure.rows[].share` | 情境假設（42%、31%、27%）；正式版用企業的員工通勤調查，或認領資料中該公司員工的入口分布 | 員工經過各入口的比例 | `assumed`；換成企業提供的資料後 `observed` | 換成「這個對象受影響的比例」：停車題是公司員工停哪個停車場、1999 是局處各類案件占比 |
| `brief.exposure.rows[].cells[]` | 熱力圖車速 | 直接取 `heatmap` 同一列 07:00–09:00 的車速 | 同熱力圖該列 | 跟著熱力圖換 |
| `brief.options[].saving` | 排隊模型 | 「協商一頁紙」段的 `effect()`：移出前後，經過瓶頸的車平均每輛排隊分鐘的差；區間對應容量上下限。維持現況為 0 | `computed` | 換成該對象在乎的效益（停車「平均找位時間」、1999「平均結案天數」） |
| `brief.options[].queue_change` | 排隊模型 | 最長排隊的變化 % | `computed` | 照用 |
| `brief.public[].value` | 網站後端（人數）；主辦方陳情資料（則數） | 人數一律 `pending`；陳情則數由 `fetch/aggregate_petitions.py` 彙總（只輸出件數，不含原文） | 人數 `pending`；陳情則數 `observed` | 陳情則數的篩選關鍵字跟著題目換 |
| `brief.operations[].value` | 企業自己的資料（門禁、停車場、出勤）；共同時段是假設 | 算得出的給數字（共同時段 = 上班時數 − 兩批時間差，7 小時）；算不出的 `pending`，並寫 `how`、`needs` | 共同時段 `assumed`；其他 `pending` | 換成該對象的營運指標；寫不出數字就照樣 `pending` 加 `how`、`needs` |

## 寫在句子或卡片裡的數字

這些不是獨立的數字欄位，但數字也要有出處：

| 位置 | 數字從哪裡來 | 換題時 |
| --- | --- | --- |
| `kpis[].note`（例如「4 天裡有 3 天」） | 熱力圖格子的 `days`、`bad_days` | 跟著熱力圖 |
| `decide.plans[].reason` | 同一份 plan 的 `saved`、`arrive_early` | 句型跟著 `decide.metric` 改 |
| `brief.conclusion.text` | `city.goal.need` 的區間、新尖峰門檻（`NEW_PEAK`） | 整句帶 `computed`，換題時重寫句型 |
| `limits.items[].why` | `sensitivity` 的 `low`、`high` | 跟著敏感度 |
| `share.templates[].text` | 網站代入 `{saved}` 等欄位，`needs` 要列出 | 句型跟著題目換 |

## 換題檢查清單

換完題目後，對照這份表確認：

- [ ] 每個標「換題時要換」的數字都換了，或明確寫「照用」。
- [ ] 熱力圖門檻依新指標重設，`legend` 寫出分界。
- [ ] 代價（`decide.metric`）、容量（`scenario.capacity`）、積壓（`queue_max`）的單位一致。
- [ ] 人數仍是 `pending`。
- [ ] 跑過 `python3 data/schema/validate.py data/mock/<新題 id>.json`。
