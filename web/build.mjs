// 把 screens/*.dc.html、src/ 與題目 JSON 打包成單一個 dist/index.html。
//
// 題目 JSON 一起內嵌，所以整個網站是一個檔案：離線也能跑完 Demo（CLAUDE.md 要求），
// 不需要額外的 fetch。換題或資料重跑後重新執行這支即可，不用改任何畫面程式。
//
//   data/processed/<id>.json → 題目 id（真實資料優先）
//   data/mock/<id>.json      → 題目 id + '-mock'（模擬資料，供對照與換題測試）
//
// 用法：node build.mjs
import { readFileSync, writeFileSync, readdirSync, mkdirSync, existsSync } from 'node:fs';

const root = new URL('.', import.meta.url);
const read = (p) => readFileSync(new URL(p, root), 'utf8');

// 畫面用 /_blob/<名稱> 引用圖片，原圖放在 assets/<名稱>.<副檔名>，build 時一律內嵌成 data URI。
// <名稱> 可以是設計稿的十六進位編號，也可以是看得懂的名字（例如 avatar-pink）。
// 零外部請求（SECURITY.md）也讓離線 Demo 能跑。換主視覺只要換 assets/ 裡的檔案，不用改程式。
const MIME = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', svg: 'image/svg+xml' };
const blobs = new Map(
  readdirSync(new URL('assets/', root))
    .filter((f) => !f.startsWith('.')) // 擋掉 macOS 的 .DS_Store 這類隱藏檔
    .map((f) => {
      const i = f.lastIndexOf('.');
      const id = f.slice(0, i);
      const ext = f.slice(i + 1);
      if (!MIME[ext]) throw new Error(`assets/${f}：不認得的圖片格式 .${ext}`);
      return ['/_blob/' + id, `data:${MIME[ext]};base64,` + readFileSync(new URL('assets/' + f, root)).toString('base64')];
    })
);
// 品牌字內嵌，網站才會零外部請求（SECURITY.md：不把使用者 IP 送給第三方；離線也要能跑完 Demo）。
// 中文不內嵌（CJK 字檔要數 MB），shell.html 裡改用系統字。
const font = 'data:font/woff2;base64,' + readFileSync(new URL('grandstander-800.woff2', root)).toString('base64');
// Inter ExtraBold：給市府與企業那幾頁的大數字。一樣內嵌，零外部請求。
const fontInter = 'data:font/woff2;base64,' + readFileSync(new URL('inter-800.woff2', root)).toString('base64');

const screens = {};
for (const f of readdirSync(new URL('screens/', root)).filter((f) => f.endsWith('.dc.html')).sort()) {
  screens[f.split('.')[0]] = read('screens/' + f).replace(/\/_blob\/[A-Za-z0-9_-]+/g, (m) => {
    if (!blobs.has(m)) throw new Error(`${f} 引用了 ${m}，但 assets/ 裡找不到對應的圖片`);
    return blobs.get(m);
  });
}

// 題目 JSON：真實資料用原本的 id，模擬資料加 -mock 後綴，兩份都內嵌讓 ?topic= 可以切換對照
const topics = {};
const collect = (dir, suffix) => {
  const url = new URL(dir, root);
  if (!existsSync(url)) return;
  for (const f of readdirSync(url).filter((f) => f.endsWith('.json')).sort()) {
    const topic = JSON.parse(read(dir + f));
    if (!topic?.meta?.id) continue; // 不是題目檔（例如 inputs/model_input.json）就跳過
    topics[topic.meta.id + suffix] = topic;
  }
};
collect('../data/processed/', '');
collect('../data/mock/', '-mock');

const DEFAULT_TOPIC = topics['t4-morning'] ? 't4-morning' : Object.keys(topics)[0];
if (!DEFAULT_TOPIC) throw new Error('找不到任何題目 JSON：確認 data/processed/ 或 data/mock/ 有檔案');

const json = (v) => JSON.stringify(v).replaceAll('</', '<\\/');

const out = read('src/shell.html')
  .replace('/*FONT*/', () => font)
  .replace('/*FONT_INTER*/', () => fontInter)
  .replace('/*TOKENS*/', () => read('src/tokens.css'))
  .replace('/*SCREENS*/', () => json(screens))
  .replace('/*TOPICS*/', () => json(topics))
  .replace('/*DEFAULT_TOPIC*/', () => json(DEFAULT_TOPIC))
  .replace('/*DATA*/', () => read('src/data.js'))
  .replace('/*RUNTIME*/', () => read('src/runtime.js'));

mkdirSync(new URL('dist/', root), { recursive: true });
writeFileSync(new URL('dist/index.html', root), out);

const list = Object.entries(topics)
  .map(([id, t]) => `${id}${t.meta.sim ? '（模擬）' : ''}`)
  .join('、');
console.log(`dist/index.html: ${Object.keys(screens).length} 個畫面、${Math.round(out.length / 1024)} KB`);
console.log(`題目：${list}；預設 ${DEFAULT_TOPIC}`);
