// 資料層：所有畫面的數字都從這裡拿，畫面裡不再寫死任何值。
//
// 兩層資料：
//   靜態層 window.__TOPICS__ — build 時內嵌的題目 JSON（歷史統計與排隊模型的結果）。
//   即時層 D.live            — /api/live 回來的現在路況，每 5 分鐘更新一次。
//
// CLAUDE.md 的界線：即時層只回答「現在多塞」，不參與推薦、不進排隊模型、不改任何結論數字。
// 取不到即時資料時，只有即時那一列顯示「暫時取不到」，其他畫面照常。
(function () {
  'use strict';

  const TOPICS = window.__TOPICS__ || {};
  const wanted = new URLSearchParams(location.search).get('topic');
  const id = TOPICS[wanted] ? wanted : window.__DEFAULT_TOPIC__;
  const T = TOPICS[id] || {};

  // ---------- 契約檢查：缺 label 或 sim 就是契約錯誤，不預設成真實 ----------
  const LABELS = ['observed', 'computed', 'assumed', 'ai'];
  const LABEL_TEXT = { observed: '真實觀測', computed: '程式計算', assumed: '情境假設', ai: 'AI 生成' };
  const errors = [];

  // 哪些物件是契約的「數字」（num 或 cell），要檢查 label 與 sim。對照 data/schema/topic.schema.json：
  //   {gap:true}                    缺口，不需要標示
  //   scenario.references[]         只要 value + text，不是契約數字（靠 text 認出來）
  //   brief.operations[]            外層只是包裝，真正的數字在它的 value 裡（物件，不是數字）
  //   kpis[]                        value 可以是字串（例如「08:30–09:15」「無」），仍要帶標示
  function looksLikeNumber(o) {
    if (o.gap === true) return false;
    if (o.pending === true) return true;
    if (typeof o.v === 'number') return true;
    if (typeof o.lo === 'number' && typeof o.hi === 'number') return true;
    if (typeof o.value === 'number' || typeof o.value === 'string') return !('text' in o);
    return false;
  }

  function audit(node, path) {
    if (Array.isArray(node)) {
      node.forEach((x, i) => audit(x, `${path}[${i}]`));
      return;
    }
    if (!node || typeof node !== 'object') return;
    if (looksLikeNumber(node)) {
      if (!LABELS.includes(node.label)) errors.push(`${path} 缺少或不認得 label（${node.label}）`);
      if (typeof node.sim !== 'boolean') errors.push(`${path} 缺少 sim`);
      else if (T.meta && T.meta.sim === true && node.sim === false) {
        errors.push(`${path} 的 sim 是 false，但 meta.sim 是 true（模擬檔不能混真實值）`);
      }
    }
    for (const k of Object.keys(node)) audit(node[k], path ? `${path}.${k}` : k);
  }
  if (T.meta) audit(T, '');

  // ---------- 數字與標籤 ----------
  /** 把契約的 num 變成畫面要的東西：text 是顯示字串，pending 時是「待補」。 */
  function num(n) {
    if (!n || typeof n !== 'object') return { text: '—', missing: true };
    if (n.pending) return { text: '待補', pending: true, unit: n.unit || '', label: n.label, sim: n.sim, note: n.note };
    const range = n.lo != null && n.hi != null && n.lo !== n.hi;
    const text = range ? `${n.lo}–${n.hi}` : n.value != null ? String(n.value) : '—';
    return { text, value: n.value, lo: n.lo, hi: n.hi, range, unit: n.unit || '', label: n.label, sim: n.sim, note: n.note };
  }

  // ---------- 熱力圖 ----------
  const heatmap = T.heatmap || {};
  const rows = heatmap.rows || [];
  const cols = heatmap.cols || [];
  const layerOf = (lid) => (heatmap.layers || []).find((l) => l.id === lid) || (heatmap.layers || [])[0];

  /**
   * 色階等級 0–5。門檻與方向都在 JSON 的 layer 裡，程式不寫死數字，也不碰色碼
   * （畫面只拿等級去設 data-level，顏色由 tokens.css 決定）。
   */
  function level(layer, v) {
    if (v == null || !layer) return null;
    const t = layer.thresholds || [];
    if (layer.direction === 'high_is_bad') {
      for (let i = 0; i < t.length; i++) if (v < t[i]) return i;
    } else {
      for (let i = 0; i < t.length; i++) if (v >= t[i]) return i;
    }
    return t.length; // 最後一級
  }

  const cell = (lid, ri, ci) => {
    const L = layerOf(lid);
    const grid = L && L.cells;
    const row = grid && grid[ri];
    return (row && row[ci]) || { gap: true };
  };

  const rowIndex = (rid) => rows.findIndex((r) => r.id === rid);
  const rowById = (rid) => rows.find((r) => r.id === rid);
  const colIndex = (cid) => cols.findIndex((c) => c.id === cid);

  // ---------- 幫你決定 ----------
  const decide = T.decide || {};
  const setup = decide.setup || {};
  const plan = (rowId, deadline) =>
    (decide.plans || []).find((p) => p.row === rowId && p.deadline === deadline);

  /**
   * 依時間彈性篩掉不能選的時段（CLAUDE.md：網站只做「篩掉不符合彈性的選項」）。
   * earlier 只留 baseline 與比它早的，later 只留 baseline 與比它晚的，none 只留 baseline。
   */
  function filterOptions(p, allows) {
    if (!p) return [];
    const opts = p.options || [];
    if (!allows || allows === 'both') return opts;
    const base = opts.findIndex((o) => o.id === p.baseline);
    if (base < 0) return opts;
    if (allows === 'none') return [opts[base]];
    return allows === 'earlier' ? opts.slice(0, base + 1) : opts.slice(base);
  }

  /** 建議的選項；彈性把它篩掉時回 baseline（照平常時間走就好）。 */
  function recommended(p, allows) {
    if (!p) return null;
    const allowed = filterOptions(p, allows);
    const rec = allowed.find((o) => o.id === p.recommended);
    return rec || allowed.find((o) => o.id === p.baseline) || allowed[0] || null;
  }

  // ---------- 錯峰情境 ----------
  const scenario = T.scenario || {};
  const result = (target, shift) =>
    (scenario.results || []).find((r) => r.target === target && r.shift === shift);

  // ---------- 即時層 ----------
  const POLL_MS = 5 * 60 * 1000;
  const live = { state: 'loading', entries: {}, updated_at: null, stale: false, error: null };
  const listeners = [];
  const onLive = (fn) => { listeners.push(fn); return () => listeners.splice(listeners.indexOf(fn), 1); };
  const notify = () => listeners.forEach((fn) => { try { fn(live); } catch (e) { /* 單一畫面壞掉不影響其他 */ } });

  let timer = null;
  async function refresh() {
    try {
      const r = await fetch('api/live', { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      live.state = 'ok';
      live.entries = j.entries || {};
      live.updated_at = j.updated_at;
      live.stale = !!j.stale;
      live.units = j.units;
      live.error = null;
    } catch (e) {
      // 取不到就說取不到，不拿歷史值假裝是現在（離線開 dist/index.html 時會走到這裡）
      live.state = 'error';
      live.error = String(e.message || e);
    }
    notify();
  }

  function startLive() {
    if (timer) return;
    refresh();
    timer = setInterval(() => { if (!document.hidden) refresh(); }, POLL_MS);
    document.addEventListener('visibilitychange', () => {
      // 回到前景且資料超過一輪沒更新就補抓一次
      if (!document.hidden && live.state !== 'loading') refresh();
    });
  }

  /** 某個入口的即時讀數；沒有偵測器或讀不到時回 null。 */
  function liveAt(rowId) {
    const e = live.entries[rowId];
    if (!e || e.gap || e.unavailable || e.speed == null) return null;
    return e;
  }

  // ---------- 現在是不是題目說的那段時間 ----------
  const toMin = (hhmm) => {
    const [h, m] = String(hhmm).split(':').map(Number);
    return h * 60 + m;
  };

  /** 現在落在哪一個時間格（回傳 cols 的索引）；不在範圍內回 -1。 */
  function currentColIndex(now) {
    const d = now || new Date();
    const mins = d.getHours() * 60 + d.getMinutes();
    for (let i = cols.length - 1; i >= 0; i--) {
      if (mins >= toMin(cols[i].label)) {
        const end = toMin((T.meta && T.meta.time_range && T.meta.time_range.end) || '23:59');
        return mins < end ? i : -1;
      }
    }
    return -1;
  }

  /** 現在是不是平日的資料時段。不是的話，畫面要寫明「現在」和「平日平均」是兩回事。 */
  function isPeakNow(now) {
    const d = now || new Date();
    const weekday = d.getDay() >= 1 && d.getDay() <= 5;
    const onlyWeekdays = !T.meta || !T.meta.days || T.meta.days.indexOf('平日') >= 0;
    return (!onlyWeekdays || weekday) && currentColIndex(d) >= 0;
  }

  /** 把 ISO 時間變成 HH:MM（給「08:46 更新」用）。 */
  const hhmm = (iso) => {
    const d = new Date(iso);
    return Number.isNaN(+d) ? '' : `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };

  window.D = {
    id,
    topics: Object.keys(TOPICS),
    meta: T.meta || {},
    heatmap,
    kpis: T.kpis || [],
    decide,
    setup,
    collective: T.collective || {},
    scenario,
    city: T.city || {},
    brief: T.brief || {},
    share: T.share || {},
    limits: T.limits || null,
    errors,

    rows,
    cols,
    rowById,
    rowIndex,
    colIndex,
    layerOf,
    level,
    cell,

    num,
    labelText: (l) => LABEL_TEXT[l] || l || '',

    plan,
    filterOptions,
    recommended,
    result,

    live,
    startLive,
    onLive,
    liveAt,

    currentColIndex,
    isPeakNow,
    hhmm,
    sourceById: (sid) => (T.meta && T.meta.sources || []).find((s) => s.id === sid),
  };
})();
