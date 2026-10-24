# 交接：web/ 網站

Oct 24, 2026 · 給接手網站的夥伴

> 先講結論：**18 個畫面都已經接上真實資料與即時路況，可以跑、可以部署。**
> 剩下的工作分三類：交件必要的（部署、主標）、品質的（斷網測試、桌機版）、加分的（認領後端）。
> 全部待辦與優先序在[第八節](#八待辦照優先序)。

---

## 一、現在在哪

| 項目 | 狀態 |
| --- | --- |
| 程式位置 | `web/`（branch `claude/web-data`，commit `cd73716`，已 push） |
| 18 個畫面 | **全部接上題目 JSON**，程式裡沒有寫死的資料陣列 |
| 即時路況 | **已接**，6 個畫面會顯示（`Main`、`Today`、`Heatmap`、`EntryMap`、`Ranking`、`City`） |
| 換題 | **可用**，三份 mock 題目都測過，不用改程式 |
| 資安 | `SECURITY.md` 交代的兩項已修，`dist/index.html` 零外部請求 |
| 分支 | **已合併 master**，領先 20 個 commit、落後 0；下一步開 PR |
| 部署 | **還沒上線**（見[第八節](#八待辦照優先序) P0-1） |

---

## 二、三分鐘跑起來

```bash
git clone <repo> && cd taipei-hackathon-2026
git config core.hooksPath .githooks     # 啟用資安 pre-commit 掃描，只要做一次
git checkout claude/web-data

cd web
node build.mjs                          # 需要 Node 18+，不用 npm install
cd dist && python3 -m http.server 4321
```

打開 <http://127.0.0.1:4321/>。**一定要用瀏覽器的裝置模擬看**（DevTools → ⇧⌘M → iPhone），
畫面是 390px 設計的，桌機全寬只會置中成一條。

本機沒有 `/api/live`（那是 Vercel 的 Serverless Function），所以即時那一列會顯示
「暫時取不到即時路況」。**這是正確行為**，不是壞掉。要測即時就 `npx vercel dev`。

### 網址可以帶參數

| 網址 | 作用 |
| --- | --- |
| `#/Heatmap` | 直接跳到某個畫面（名稱＝`screens/` 的檔名） |
| `?topic=t4-morning-mock` | 換成模擬資料的版本（對照用） |
| `?topic=b1-1999-mock#/City` | 兩個可以一起用 |

### 改完要跑的

```bash
node src/screens.test.mjs                        # 18 個畫面的自動檢查
node src/screens.test.mjs Heatmap                # 只看一個
node src/screens.test.mjs --topic b1-1999-mock   # 換題測試，最會抓到問題的一支
node build.mjs                                   # 重新打包
```

**這四條在 commit 前都要綠。** 尤其換題測試：它用的是完全不同形狀的題目（1999 市民專線，
沒有車速、沒有「早到幾分」），最容易抓出「你又把某個欄位當成一定存在」。

---

## 三、架構：兩層資料

```
build 時 ─→ data/processed/*.json ─┐
            data/mock/*.json      ─┴→ 內嵌進 dist/index.html ─→ window.__TOPICS__
                                                                     │
                                                                     ▼
                                                                   D.*  ──→ 18 個畫面
                                                                     ▲
每 5 分鐘 ─→ fetch('api/live') ──→ Vercel Function ──→ 交工處 VD ──→ D.live
```

**靜態層**（題目 JSON）：歷史統計與排隊模型的結果。整份內嵌進單一個 HTML，所以離線也能跑完 Demo。

**即時層**（`/api/live`）：只回答「現在多塞」。

> **界線（CLAUDE.md 的即時層條款，請務必遵守）：**
> 即時資料**不參與推薦、不進排隊模型、不改任何結論數字**。
> 畫面上的建議、情境、敏感度、城市行動，一律只能來自題目 JSON。
> 即時掛掉時只有即時那一列顯示「暫時取不到」，其他畫面照常。

為什麼要這條：即時值會跳（1 分鐘的樣本很小），如果讓它影響推薦，同一個人每隔幾分鐘重開
會拿到不同建議；而且 Demo 當天若 VD 掛掉，整個作品就垮了。

---

## 四、檔案地圖

| 路徑 | 是什麼 | 要改的時候 |
| --- | --- | --- |
| `screens/*.dc.html` | 18 個畫面。`<x-dc>` 模板 ＋ `<helmet>` CSS ＋ `class Component` | 改版面或改某頁顯示什麼 |
| `src/data.js` | **資料層**，掛 `window.D`。挑題目、驗契約、算色階、查 plan 與情境、合併即時 | 要加新的資料查詢函式 |
| `src/runtime.js` | 迷你執行層：模板、DOM diff、路由、localStorage、`window.app` | 很少需要改 |
| `src/tokens.css` | 色階、發散色階、資料標籤、斜線紋路 | 設計交付 `design/tokens.css` 後來這裡換值 |
| `src/shell.html` | 外框、共用樣式、內嵌字型 | 加全站共用的樣式 |
| `src/screens.test.mjs` | 自動檢查 | 想加新的檢查規則 |
| `api/live.js` | 即時 VD 代理 | 要加國道 TDX 的時候 |
| `build.mjs` | 打包 | 要內嵌新的東西（圖、字型） |
| `grandstander-800.woff2` | 品牌字，22 KB，SIL OFL 授權 | 不用動 |

---

## 五、寫畫面的規則

### 一定要遵守

1. **不要寫死任何資料。** 數字、地點名稱、時段、單位、天數 —— 全部從 `D.*` 讀。
   換題測試會抓到。
2. **不要寫死色階色碼。** 用 `D.level(layer, v)` 拿等級 0–5，放進 `data-level="..."`，
   顏色由 `tokens.css` 決定。
   ```html
   <!-- 對 --> <div class="cell" data-level="{{c.level}}"></div>
   <!-- 錯 --> <div style="background: {{c.bg}}"></div>
   ```
3. **選填欄位要防呆。** 這些在別的題目可能不存在：
   `layer.bad_at`、`cell.days`、`cell.lo`／`hi`、`option.arrive_early`、`limits`、`share`、`heatmap.aux`。
4. **缺口留白。** `{gap: true}` 的格子不補值，顯示空白或虛線框。Demo 台詞是
   「沒有偵測器的地方我們留白，不補數字」。
5. **模擬加斜線。** `sim: true` 的格子加 `class="hatch"`。
6. **人數一律「尚無資料」。** JSON 裡是 `pending`，不要放任何模擬人數。

### 常用的 D API

```js
D.meta, D.heatmap, D.kpis, D.decide, D.setup, D.collective,
D.scenario, D.city, D.brief, D.share, D.limits   // 契約的區塊，直接對應

D.rows, D.cols                 // 地點、時段
D.rowById(id), D.rowIndex(id)  // 查列
D.layerOf('speed')             // 圖層（speed / flow）
D.level(layer, v)              // → 0–5，給 data-level 用
D.cell('speed', ri, ci)        // → {v,lo,hi,days,bad_days,label,sim} 或 {gap:true}
D.num(n)                       // 契約的 num → {text,value,lo,hi,range,unit,label,sim,pending}
D.plan(rowId, deadline)        // 查一份建議
D.filterOptions(plan, allows)  // 依時間彈性篩時段
D.recommended(plan, allows)    // 建議的那個；被彈性篩掉就回 baseline
D.result(target, shift)        // 查情境結果
D.labelText('observed')        // → '真實觀測'

D.live                         // {state:'loading'|'ok'|'error', updated_at, stale, entries}
D.liveAt(rowId)                // 某個入口的即時讀數；沒有回 null
D.isPeakNow()                  // 現在是不是平日的資料時段
D.hhmm(iso)                    // → 'HH:MM'
D.errors                       // 契約錯誤清單
```

### 要用即時資料的畫面

在 class 上加一行，執行層就會在即時資料更新時自動重畫：

```js
class Component extends DCLogic {
  usesLive = true;
  ...
}
```

---

## 六、容易踩的坑

執行層是 227 行的自製迷你框架，有幾個和 React／Vue 不一樣的地方：

| 坑 | 說明 |
| --- | --- |
| **`{{}}` 不是 JS** | 只支援點路徑 `{{a.b.c}}`。不能寫 `{{a + b}}`、`{{a ? b : c}}`、不能呼叫函式。運算一律在 `renderVals()` 裡算好 |
| **`sc-for`／`sc-if` 的值要是單一 `{{}}`** | `<sc-if value="{{flag}}">` 可以；`<sc-if value="x{{flag}}">` 不行 |
| **屬性是 `false` 或 `null` 就整個不輸出** | 所以 `disabled="{{c.gap}}"` 在 `gap` 為 false 時不會留下 `disabled` 屬性。想輸出 `"0"` 要注意 `0` 是會輸出的（只有 `false`／`null` 會被跳過） |
| **清單沒有 key** | DOM diff 用 index 對位。清單長度變動沒問題，但**重排**會錯位。目前所有清單長度固定 |
| **`onClick="{{fn}}"` 要給函式** | 在 `renderVals()` 回傳 `pick: () => this.setState({...})` |
| **`<helmet>` 裡只有 `<style>` 會被用** | `<link>`、`<script>` 都會被丟掉。想加全站樣式請改 `src/shell.html` |
| **`support.js` 不存在** | 每個 `.dc.html` 開頭的 `<script src="./support.js">` 是設計畫布的殘留，執行層不讀它 |
| **自動檢查會把每個函式呼叫一次** | 所以 `pick()` 之類的不要有「只能呼叫一次」的假設 |
| **改完一定要 `node build.mjs`** | 直接改 `screens/` 不會反映到 `dist/index.html` |

---

## 七、資料的真相（最重要的一節）

### 設計稿上的數字全部是模擬的

`design/traffic-gem-screens/README.md` 自己就寫了：「數字取自 `data/mock/t4-morning.json`，
**全部是模擬資料**」。**不要照抄設計稿的數字**，也不要用它來判斷畫面對不對。

### 真實資料比設計稿平很多

19 個上班日（09/23–10/22，已排除週末、國定假日與 10/23 颱風假）的 VD 平均車速：

| 入口 | 07:00 | 08:00 | 08:30 | 09:00 |
| --- | --- | --- | --- | --- |
| 內湖路一段 | 41 | 33 | 29 | 30 |
| 堤頂大道 | 61 | 45 | 48 | 47 |
| 民權大橋 | 28 | 30 | 28 | 30 |
| 成美橋 | 46 | 47 | 46 | 45 |
| 環東大道 | 73 | 52 | 47 | 52 |
| 國 1 內湖交流道**（模擬）** | 58 | 27 | **16** | 41 |

**沒有任何一格低於 20 km/h。** KPI 的「尖峰集中時段」真實值是**「無」**。
畫面上唯一看起來很塞的那一列，是模擬資料。

**為什麼？** `limits` 的第一項已經寫了：偵測器量到的是**通過的車**，不是**想進來的車**。
塞住時車過不去，偵測器數不到；數得到的那些車速度自然不慢。

**有晨峰形狀的是流量**（輛／15 分鐘）：

| 入口 | 07:00 | 07:30 | 08:00 |
| --- | --- | --- | --- |
| 環東大道 | 489 | **743** | 671 |
| 國 1 內湖交流道 | 381 | 457 | **724** |

→ **主標「早上八點半，車都卡在哪裡？」現在站不住，要改。**
Yasmine 還沒決定方向。兩個選項：
- (a) 熱力圖主圖層從「車速」改成「流量」，主標改講流量尖峰
- (b) 維持車速，主標改成誠實版本（例如「VD 量到的，和你的體感不一樣」）並把 `limits` 拉到前面

### 資料檔會被資料端重跑

`data/processed/t4-morning.json` 在我作業的幾小時內被重新產生**四次**（天數 20→21→22→19）。
資料端重跑後，**網站要重跑 `node build.mjs` 才會跟著變**。不要以為數字對不上是 bug。

---

## 八、待辦（照優先序）

### P0 — 交件必要（10/24 16:00 前）

1. **部署到 Vercel 拿到公開網址。**
   Import Project 時 **Root Directory 要設成 `web`**。`vercel.json` 已經設定好 Build Command
   與 Output Directory，`api/live.js` 會自動被辨識成 Serverless Function。
   部署後驗收：
   ```bash
   curl -s https://<網址>/api/live | jq '.updated_at, .entries["tiding-n"]'
   curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<網址>/api/live   # 要是 405
   ```
2. **決定主標與 Demo 台詞**（見[第七節](#七資料的真相最重要的一節)）。這是內容決定，不是程式。
3. **更新交件文件**：`README.md` 補作品網址與 Demo 操作說明。
   `data/SOURCES.md` 的開源套件清單我已經補好了。

### P1 — 品質

4. **斷網測試。** 關掉 Wi-Fi 用真的瀏覽器開 `dist/index.html`，走過 18 個畫面，
   確認字型與版面都正常、只有即時那一列顯示取不到。
   我只驗過「檔案裡沒有外部網址」，沒有實際斷網跑過。
5. **真機測試。** iPhone Safari 與 Android Chrome 各開一次，確認沒有橫向捲動、
   底部分頁不會被系統手勢列蓋住。
6. **協商一頁紙 `/brief`。** JSON 的 `brief` 區塊資料完整（結論、三種做法、營運影響、
   試辦設計、民意依據），但**沒有畫面**。Demo 腳本第 3 段要用。
   做的話要注意：列印要剛好一頁 A4，需要另寫 `@media print`。

### P2 — 加分

7. **時段認領後端。** 現在所有人數都顯示「尚無資料」。
   介面需求見 `SCREENS.md` 的「認領後端」。
   **做之前先讀 `SECURITY.md` 第三節**：只能存日期、入口、時段、匿名裝置代碼，
   不存 IP、不存個資，要有頻率限制，Demo 用獨立房間。
8. **設定加「從哪裡出發」一步。** `decide.setup.origins` 的資料已經在 JSON 裡，
   City 的「大家從哪裡來」也等著它。但這是新功能，要先問 Yasmine（範圍凍結）。
9. **國 1 內湖交流道的即時資料。** 需要 TDX 金鑰設到 Vercel 環境變數。
   **注意：`SECURITY.md` 第七節記著 TDX 金鑰 10/24 08:07 起已失效**，要先去重新產生。

---

## 九、分支狀況（動手前先看）

```
origin/claude/web-data     ←─ 這裡（網站 + 已合併 master）
origin/master              ←─ 落後，等這個分支的 PR 合回去
origin/claude/relaxed-dirac-ysp1hu   ←─ 另一個作業，還在動
```

- **master 已經在 10/24 合進來了**（commit `a63d512`），目前**領先 master 20 個 commit、落後 0 個**。
- 當時的衝突在 `build_all.py` 與 `build_vd_15min.py`：兩邊都在改「哪些天算平日」，
  但各做一半 —— master 排除週末與國定假日，本分支排除颱風假並只算往內湖方向的路段。
  **解法是兩個條件同時成立**，不是二選一。
- 連帶修正了一個資料錯誤：原本的 22 天裡混進了 09/25 中秋、09/28 教師節、10/09 國慶補假，
  **現在是 19 個上班日**。最塞的一格從 27 改成 28 km/h。
- 下一步是開 PR 把 `claude/web-data` 合回 `master`。
- 同時間有別的作業在改這個 repo。開工前先 `git fetch` 看一下。

---

## 十、團隊習慣

| 項目 | 規則 |
| --- | --- |
| 語言 | 文件、註解、commit 訊息、對話一律**繁體中文（台灣用語）** |
| 分支 | 在 `claude/<名稱>` 上做，PR 合回 `master`。不直接推 master |
| commit 訊息 | 一行講清楚**做了什麼與為什麼**，例如「gen_t4_morning：真實資料算不出排隊時，情境改用假設模型而不是當掉」 |
| 資安閘門 | `git config core.hooksPath .githooks` 做一次。被擋下時**不要用 `--no-verify`**，先確認是不是誤判 |
| 文件風格 | 開頭寫標題與日期對象、大量用表格、檔名與欄位用反引號、不確定的事要寫明「推測」「待確認」 |
| 民眾畫面用字 | 國中程度 5 秒看懂（對照 `design/plain-copy.md`）。講的是「**經過入口的時間**」，不是「出門時間」 |
| 契約 | `data/schema/topic.schema.json` 是 v1，**只能新增欄位，不改名、不刪**。要改要資料與網站兩人同意 |
| 抓市府資料 | **每 5 分鐘最多一次**，而且要確保別人沒辦法逼它更頻繁 |

### 幾份必讀

| 文件 | 什麼時候看 |
| --- | --- |
| [`CLAUDE.md`](../CLAUDE.md) | **最先看。** 不能破的規則都在這 |
| [`SECURITY.md`](../SECURITY.md) | 動後端、抓資料、commit 之前 |
| [`web/README.md`](../web/README.md) | 網站的技術細節 |
| [`data/schema/README.md`](../data/schema/README.md) | 要讀 JSON 的哪個欄位時 |
| [`SCREENS.md`](../SCREENS.md) | 原始的畫面規格（注意：和現在的實作有落差，實作是 18 個手機畫面，規格寫的是 8 個手機＋桌機） |
| [`PRODUCT.md`](../PRODUCT.md) | Demo 怎麼講 |

---

## 十一、我沒做到的事（誠實記錄）

- **沒有用真的瀏覽器看過畫面。** 我的驗證都是程式層的（18 個畫面 × 4 個題目的
  `renderVals()` 檢查、契約檢查正反向、即時 API 與 Python 算法對帳）。
  **版面是否跑掉、顏色對不對、手機上好不好點，都還沒有人看過。** 這是最大的風險。
- **沒有斷網測試。**
- **沒有部署。**
- **主標還是舊的**（「早上八點半，車都卡在哪裡？」），和真實資料不符。
- **桌機版完全沒有。** `SCREENS.md` 規格裡的 4 個桌機畫面（熱力儀表板、錯峰情境、
  協商一頁紙、我們可能錯在哪）在實作裡是手機版，從選單的「給市府與企業」進入。
- **畫面 JS 裡還有少數 UI 色碼**（標籤底色、狀態色）。色階的色碼已經全部移到
  `tokens.css`，但這些還沒有。
