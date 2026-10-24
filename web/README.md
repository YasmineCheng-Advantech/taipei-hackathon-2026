# Traffic Gem 網站

Oct 24, 2026 · 給接手網站的人

> 手機優先的單頁網站，18 個畫面。**所有數字都來自題目 JSON 與即時 VD，畫面程式裡不寫死任何資料。**

## 一頁摘要

| 項目 | 說明 |
| --- | --- |
| 技術 | 零相依套件。`node build.mjs` 把畫面、執行層與題目 JSON 打包成單一個 `dist/index.html` |
| 需求 | Node 18+。`npm install` 不會裝任何東西 |
| 靜態資料 | `../data/processed/*.json`（真實）與 `../data/mock/*.json`（模擬，id 加 `-mock`），build 時內嵌 |
| 即時資料 | `api/live.js`（Vercel Serverless Function）每 5 分鐘從臺北市交工處 VD 取現在的車速 |
| 換題 | **只換 JSON，不改程式。** 重跑資料後執行 `node build.mjs` 即可 |

## 常用指令

```bash
node build.mjs                      # 打包成 dist/index.html
node src/screens.test.mjs           # 18 個畫面的自動檢查
node src/screens.test.mjs Heatmap   # 只檢查一個畫面
node src/screens.test.mjs --topic b1-1999-mock   # 換題測試：別的題目也要能跑

cd dist && python3 -m http.server 4321   # 本機看（用瀏覽器裝置模擬，iPhone 390px）
```

網址可以加 `?topic=<id>` 切換題目、`#/<畫面名>` 直接跳頁，例如
`http://127.0.0.1:4321/?topic=t4-morning-mock#/Heatmap`。

## 檔案

| 路徑 | 內容 |
| --- | --- |
| `screens/*.dc.html` | 18 個畫面。每個是設計畫布的原生格式：`<x-dc>` 模板 ＋ `<helmet>` CSS ＋ `class Component` |
| `src/data.js` | **資料層**。挑題目、驗契約、算色階等級、查 plan 與情境結果、合併即時資料。掛在 `window.D` |
| `src/runtime.js` | 迷你執行層：`{{}}`、`<sc-for>`、`<sc-if>`、DOM diff、hash 路由、localStorage |
| `src/tokens.css` | 視覺規範：6 級色階、發散色階、四種資料標籤、斜線紋路。**程式不碰色碼**，只設 `data-level` |
| `src/shell.html` | 外框與共用樣式；`/*TOKENS*/` `/*SCREENS*/` `/*TOPICS*/` `/*DATA*/` `/*RUNTIME*/` 由 build 填入 |
| `src/screens.test.mjs` | 在 Node 裡跑每個畫面的 `renderVals()`，抓 undefined／NaN／互動爆掉 |
| `api/live.js` | 即時 VD 代理 |
| `build.mjs` | 打包 |

## 兩層資料

```
build 時 ─→ 題目 JSON 內嵌 ─→ window.__TOPICS__ ─→ D.*  ─→ 18 個畫面
                                                    ↑
每 5 分鐘 ─→ fetch('api/live') ─────→ D.live ──────┘
```

**界線（CLAUDE.md 的即時層條款）：即時只回答「現在多塞」，不參與推薦、不進排隊模型、不改任何結論數字。**
即時取不到時，只有即時那一列顯示「暫時取不到即時資料」，其他畫面照常 —— 所以離線也能跑完 Demo。

用到即時資料的畫面：`Today`、`Heatmap`、`EntryMap`、`Ranking`。（首頁 `Main` 照設計稿是純主視覺，不放即時列。）
它們在 class 上宣告 `usesLive = true`，即時資料更新時執行層會自動重畫。

### 即時車速的算法

和 `data/fetch/collect_vd.py` 一致（依車道車輛數加權平均），**但多一條**：排除車速回報 0 的車道。
有車經過卻回報 0 km/h 是量測缺失，不是車停住了；歷史資料是 15 分鐘 × 多天的平均，雜訊會被洗掉，
即時只有 1 分鐘的樣本，一個零速車道就會把數字拉到荒謬的值。同時回報 `samples` 與 `low_sample`，
車太少時畫面要說「測不準」，而不是給一個看起來精確的數字。

## 寫畫面時要遵守的事

- **不要寫死數字、地點名稱、時段、單位**，一律從 `D.*` 讀。換題測試（`--topic b1-1999-mock`）會抓到。
- **不要寫死色階色碼。** 用 `D.level(layer, v)` 取得等級 0–5，放進 `data-level`，顏色由 `tokens.css` 決定。
- **選填欄位要防呆**：`bad_at`、`days`、`lo`／`hi`、`arrive_early`、`limits`、`share` 在別的題目可能沒有。
- **缺口留白**：`{gap: true}` 的格子不補值，顯示空白或虛線框。
- **模擬加斜線**：`sim: true` 的格子加 `hatch` class。
- **人數一律向後端拿**：JSON 裡是 `pending`，顯示「尚無資料」，不放模擬值。

## 部署

Vercel，**Root Directory 設成 `web`**。`vercel.json` 已設定 Build Command `npm run build`、Output Directory `dist`。
`api/live.js` 會自動被辨識成 Serverless Function。

## 和設計稿的關係

`screens/` 是**正式實作**，從 `design/traffic-gem-screens/` 複製後改成讀資料，兩邊已經分歧。
設計稿只保留版面與互動方式；**設計稿裡的數字全部是模擬的**（見 `design/traffic-gem-screens/README.md`），不要照抄。

## 還沒做到的

- **時段認領後端沒有做。** 所有人數顯示「尚無資料」。
- **協商一頁紙 `/brief` 沒有畫面**，雖然 JSON 的 `brief` 區塊有完整資料。
- **國 1 內湖交流道沒有即時資料**（國道資料取不到（TDX 免費額度已於 2026-10-24 用完、金鑰失效）），熱力圖上標示為模擬。
- **設定沒有「從哪裡出發」這一步**，所以 `city.breakdowns` 的「大家從哪裡來」拿不到使用者的選擇。
- 畫面 JS 裡仍有少數 UI 用途的色碼（標籤底色、狀態色）；**色階的色碼已經全部移到 `tokens.css`**。
