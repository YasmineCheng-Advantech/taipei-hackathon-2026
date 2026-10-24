# 交代單：web/ 的兩個資安修正

Oct 24, 2026 · 給正在改 `web/` 的人（另一個 Claude 帳號）

> **狀態：兩項都在 2026-10-24 修好了**，驗收結果見每一節最後。這份保留下來，說明當初的問題與修法。
> 背景規則見 [`SECURITY.md`](../SECURITY.md)。兩項都不影響版面，只改行為。

## 一、`web/api/live.js`：擋住對市府系統的放大（**優先**）

### 問題

這支是臺北市交工處 `VDLive.xml`（1.7 MB）的伺服器端代理，用 `Cache-Control: s-maxage=300` 來守 CLAUDE.md 的「每 5 分鐘最多抓一次」。

但 **CDN 的快取鍵包含 query string**。所以：

```
/api/live?x=1   → cache miss → 打交工處
/api/live?x=2   → cache miss → 打交工處
/api/live?x=3   → cache miss → 打交工處
```

任何人都能用一個迴圈把我們的函式變成對市府系統的放大器。投票期是公開網址，這不是假想情境。這會違反 CLAUDE.md 的「不對市府或第三方系統做掃描、壓測」。

### 修法（三個都要）

**1. 忽略 query string ＋ 伺服器端節流。** 不要只靠 CDN，模組層自己記住上次的結果：

```js
// 模組層快取：同一個 serverless 實例在 TTL 內不重複打上游。
// 這是第二道；第一道仍是 CDN 的 s-maxage，兩個都要。
const TTL_MS = 5 * 60 * 1000;
let cached = null;        // { at: number, body: object }
let inflight = null;      // 併發時共用同一個請求，不要各打各的

async function fetchUpstream() {
  if (cached && Date.now() - cached.at < TTL_MS) return cached.body;
  if (inflight) return inflight;                       // 已經有人在抓，跟著等
  inflight = (async () => {
    const r = await fetch(SOURCE, { signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
    if (!r.ok) throw new Error(`上游回應 ${r.status}`);
    const parsed = parse(await r.text());
    if (!parsed.updatedAt) throw new Error('讀不到 UpdateTime');
    cached = { at: Date.now(), body: parsed };
    return parsed;
  })().finally(() => { inflight = null; });
  return inflight;
}
```

> 注意：serverless 會有多個實例，模組層快取**不保證**全域只有一個請求。它的作用是把「同一實例被 query string 洗快取」的放大倍數壓下來。真正的上限靠 CDN 的 `s-maxage`，所以兩個都要留。

**2. 限定 method。** 非 `GET`／`HEAD` 回 405：

```js
if (req.method !== 'GET' && req.method !== 'HEAD') {
  res.setHeader('Allow', 'GET, HEAD');
  return res.status(405).json({ error: '只支援 GET' });
}
```

**3. 錯誤訊息不外洩。** 現在這行會把上游的原始錯誤回給前端：

```js
return res.status(503).json({ error: '暫時取不到即時資料', detail: String(e.message || e) });
//                                                          ^^^^^^ 拿掉
```

改成對外固定訊息，詳情只寫 server log：

```js
console.error('[live] 取不到上游資料:', e);
return res.status(503).json({ error: '暫時取不到即時資料' });
```

### 驗收

- [x] `/api/live?x=1`、`?x=2`、`?x=3` 連續打，只有**一次**對上游的請求（用假的 fetch 驗過）
- [x] `POST /api/live` 回 405，並帶 `Allow: GET, HEAD`
- [x] 上游故障時只有「現在路況」那一列顯示「暫時取不到」，其他畫面照常
- [x] 回應裡不含上游的錯誤字串（只回 `{"error":"暫時取不到即時資料"}`，詳情寫 `console.error`）

## 二、`web/src/shell.html`：字型改離線

### 問題

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Grandstander...&family=Noto+Sans+TC...">
```

這是整個網站**唯一的外部請求**。兩個問題：

1. **隱私**：每位使用者的 IP 都會送給 Google。我們對外說「不收集個資」，這跟那個說法有張力。
2. **Demo 穩定性**：CLAUDE.md 明訂「離線也要能跑完 Demo」。現在斷網會掉字型，版面會跑掉。

### 修法

| 字型 | 用在哪 | 做法 |
| --- | --- | --- |
| `Grandstander` 800 | 品牌字，18 個畫面都有 | **內嵌**。Latin-only，woff2 約 20–40 KB。照 `build.mjs` 既有的 `hero.webp` base64 手法做 |
| `Noto Sans TC` | 內文中文 | **不內嵌**（自架 CJK 要數 MB）。改用系統字堆疊 |

中文改成系統字堆疊，macOS／iOS 會用 PingFang TC、Windows 用微軟正黑體，視覺差異很小：

```css
font-family: 'PingFang TC', 'Microsoft JhengHei', 'Noto Sans TC', sans-serif;
```

`build.mjs` 內嵌 Grandstander 的做法（沿用現有寫法）：

```js
const font = 'data:font/woff2;base64,' + readFileSync(new URL('grandstander-800.woff2', root)).toString('base64');
// shell.html 裡放一個 /*FONT*/ 佔位，用 @font-face 的 src: url(...) 接上
```

最後把 `shell.html` 的 `preconnect` 與 stylesheet `<link>` 兩行刪掉。

### 驗收

- [x] `dist/index.html` 裡沒有任何 `http(s)://` 的 `src`／`href`／`url()`，唯一的對外呼叫是 `fetch('api/live')`（同網域）
- [x] Grandstander 800 內嵌（22 KB，`data:font/woff2`），中文用系統字堆疊
- [x] 已記進 [`data/SOURCES.md`](../data/SOURCES.md)：Grandstander 為 SIL OFL 1.1
- [ ] **還沒做**：關掉 Wi-Fi 用真的瀏覽器開一次，確認 18 個畫面版面都正常（建議交件前做）

### 補充：前端的 `cache: 'no-store'`

`web/src/data.js` 第 138 行是 `fetch('api/live', { cache: 'no-store' })`。這只影響**瀏覽器自己的**快取，不會穿透 CDN 的 `s-maxage`。但部分 CDN 會理會用戶端送來的 `Cache-Control: no-cache` 而回源，所以上面第 1 項的「模組層節流」更重要——有它在，就算每個請求都回源，打到交工處的仍然是 5 分鐘一次。

## 三、順手的小事（不急）

~~`web/src/runtime.js` 的 `window.claude.use('downloads')` 是 claude.ai artifact 的殘留。~~ **10/24 已清掉**，改成單純的 `<a download>`，並補上 `URL.revokeObjectURL`。

## 四、commit 前要知道的

repo 已經裝了兩層資安閘門，你 commit 時會自動跑：

- Claude Code hook（`.claude/settings.json`）：攔 `git commit` / `git push`
- git pre-commit hook：`git config core.hooksPath .githooks` 啟用一次

被擋下時訊息會說明是哪一條規則。**不要用 `--no-verify` 繞過**，先確認是不是誤判。
