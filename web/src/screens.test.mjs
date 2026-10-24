// 把每個畫面的 class Component 在 Node 裡跑一遍，檢查 renderVals() 不會爆、也不會吐出 undefined。
// 畫面長相要用瀏覽器看，但「資料接錯」這類錯誤這支就抓得到。
//
// 用法：node src/screens.test.mjs            檢查全部畫面（預設題目）
//      node src/screens.test.mjs Heatmap     只檢查一個
//      node src/screens.test.mjs --topic t4-morning-mock
import { readFileSync, readdirSync } from 'node:fs';

const args = process.argv.slice(2);
const ti = args.indexOf('--topic');
const topicId = ti >= 0 ? args[ti + 1] : 't4-morning';
const only = args.filter((a, i) => !a.startsWith('--') && !(ti >= 0 && i === ti + 1));

// ---- 載入資料層（和瀏覽器同一份 src/data.js）----
const topics = {};
for (const [dir, suffix] of [['../../data/processed/', ''], ['../../data/mock/', '-mock']]) {
  for (const f of readdirSync(new URL(dir, import.meta.url)).filter((f) => f.endsWith('.json'))) {
    const t = JSON.parse(readFileSync(new URL(dir + f, import.meta.url), 'utf8'));
    if (t?.meta?.id) topics[t.meta.id + suffix] = t;
  }
}
global.window = { __TOPICS__: topics, __DEFAULT_TOPIC__: topicId };
global.location = { search: '', href: 'http://localhost/' };
global.document = { hidden: false, addEventListener() {} };
global.confirm = () => false; // 測試不真的刪資料
global.alert = () => {};
global.prompt = () => null;
global.fetch = async () => { throw new Error('node 沒有 /api/live'); };
global.setInterval = () => 0;
eval(readFileSync(new URL('data.js', import.meta.url), 'utf8'));
const D = window.D;

// ---- 畫面需要的最小 app 替身 ----
const store = {};
const app = {
  load: (k) => ({ ...(store[k] || {}) }),
  save: (k, v) => { store[k] = v; },
  reset() {},
  go() {}, toast() {}, share() {}, saveCard() {},
  profile() {
    const rowIds = D.setup.rows || [];
    const row = D.rowById(rowIds[0]) || {};
    const flex = (D.setup.flex || [])[0] || {};
    return {
      rowId: rowIds[0], row, entry: row.name || '', entrySub: row.sub || '',
      dl: 0, deadline: (D.setup.deadlines || [])[0] || '',
      flexId: flex.id, flex: flex.label || '', allows: flex.allows || 'both',
      constraints: [], reasons: '沒有', origin: null, consent: false,
    };
  },
  summary() { return app.profile().entry; },
  today() {
    const p = app.profile();
    const plan = D.plan(p.rowId, p.deadline);
    return { profile: p, plan, rec: D.recommended(plan, p.allows), options: D.filterOptions(plan, p.allows) };
  },
};
class DCLogic {
  constructor() { this.state = {}; }
  setState(patch) { this.state = { ...this.state, ...(typeof patch === 'function' ? patch(this.state) : patch) }; }
  renderVals() { return {}; }
}

// ---- 走訪 renderVals() 的結果，找出 undefined 與 NaN ----
function findBad(v, path, out, seen = new Set()) {
  if (v === undefined) { out.push(`${path} 是 undefined`); return; }
  if (typeof v === 'number' && Number.isNaN(v)) { out.push(`${path} 是 NaN`); return; }
  if (typeof v === 'string' && /undefined|NaN|\[object Object\]/.test(v)) out.push(`${path} 的字串含 "${v.match(/undefined|NaN|\[object Object\]/)[0]}"：${v.slice(0, 70)}`);
  if (!v || typeof v !== 'object' || seen.has(v)) return;
  seen.add(v);
  if (Array.isArray(v)) v.forEach((x, i) => findBad(x, `${path}[${i}]`, out, seen));
  else for (const k of Object.keys(v)) { if (typeof v[k] !== 'function') findBad(v[k], `${path}.${k}`, out, seen); }
}

const dir = new URL('../screens/', import.meta.url);
const files = readdirSync(dir).filter((f) => f.endsWith('.dc.html')).sort();
let failed = 0;
let checked = 0;

for (const f of files) {
  const name = f.split('.')[0];
  if (only.length && !only.includes(name)) continue;
  checked++;
  const html = readFileSync(new URL(f, dir), 'utf8');
  const m = html.match(/<script type="text\/x-dc"[^>]*>([\s\S]*?)<\/script>/);
  if (!m) { console.log(`✗ ${name}：找不到 class Component`); failed++; continue; }
  try {
    const Component = new Function('DCLogic', 'app', 'D', '"use strict";\n' + m[1] + '\nreturn Component;')(DCLogic, app, D);
    const inst = new Component();
    const vals = inst.renderVals() || {};
    const bad = [];
    findBad(vals, '', bad);
    // 把每個 pick/toggle 點一次，確認互動不會爆
    let clicks = 0;
    const clickAll = (v, depth = 0) => {
      if (depth > 4 || !v || typeof v !== 'object') return;
      for (const k of Object.keys(v)) {
        if (typeof v[k] === 'function') { try { v[k]({ target: { value: 0 } }); clicks++; } catch (e) { bad.push(`${k}() 丟出 ${e.message}`); } }
        else clickAll(v[k], depth + 1);
      }
    };
    clickAll(vals);
    if (bad.length) { failed++; console.log(`✗ ${name}`); bad.slice(0, 6).forEach((b) => console.log(`    ${b}`)); }
    else console.log(`✓ ${name}（${Object.keys(vals).length} 個值、${clicks} 個互動）`);
  } catch (e) {
    failed++;
    console.log(`✗ ${name}：${e.message}`);
  }
}

console.log(`\n題目 ${topicId}｜契約錯誤 ${D.errors.length} 項｜檢查 ${checked} 個畫面，${failed} 個有問題`);
process.exit(failed ? 1 : 0);
