// Traffic Gem — tiny runtime that renders the *.dc.html design screens as a working app.
// Supports the subset the screens use: {{path}} interpolation, <sc-for list as>, <sc-if value>,
// onClick / onChange handlers, and `class Component extends DCLogic` with state + setState.
(function () {
  'use strict';

  const SCREENS = window.__SCREENS__;            // { Name: '<html source>' }
  const D = window.D;                            // 資料層：所有數字都從這裡拿
  const HOME = 'Main';
  const STORE_KEY = 'traffic-gem:v1';

  // ---------- 使用者設定（只存在這支手機）----------
  // 入口、最晚到達、彈性、原因的選項全部來自題目 JSON，換題只換資料、不改這裡。
  let store = {};
  try { store = JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch (e) { store = {}; }
  const persist = () => { try { localStorage.setItem(STORE_KEY, JSON.stringify(store)); } catch (e) { /* private mode */ } };

  const app = {
    load: (key) => ({ ...(store[key] || {}) }),
    save: (key, val) => { store[key] = val; persist(); },
    reset: () => { store = {}; persist(); },
    /** 使用者的設定攤平成畫面好用的樣子；選項對不上 JSON 時退回第一個，不會壞掉。 */
    profile() {
      const s = { dl: 0, ...store.Setup };
      const r = { on: {}, consent: false, ...store.Reasons };
      const rowIds = D.setup.rows || [];
      const rowId = rowIds.includes(s.row) ? s.row : rowIds[0];
      const row = D.rowById(rowId) || {};
      const deadlines = D.setup.deadlines || [];
      const dl = Math.min(Math.max(0, s.dl | 0), Math.max(0, deadlines.length - 1));
      const flexList = D.setup.flex || [];
      const flex = flexList.find((f) => f.id === s.flex) || flexList[0] || {};
      const constraints = (D.setup.constraints || []).filter((c) => r.on[c.id]);
      const origin = (D.setup.origins || []).find((o) => o.id === s.origin) || null;
      return {
        rowId, row, entry: row.name || '', entrySub: row.sub || '',
        dl, deadline: deadlines[dl] || '',
        flexId: flex.id, flex: flex.label || '', allows: flex.allows || 'both',
        constraints, reasons: constraints.length ? constraints.map((c) => c.label).join('、') : '沒有',
        origin, consent: !!r.consent,
      };
    },
    summary() {
      const p = app.profile();
      return p.entry + '・上午 ' + p.deadline + ' 前到・' + p.flex;
    },
    /** 今天這一份建議（同一天重開要看到同一個，不會一直往後延）。 */
    today() {
      const p = app.profile();
      const plan = D.plan(p.rowId, p.deadline);
      return { profile: p, plan, rec: D.recommended(plan, p.allows), options: D.filterOptions(plan, p.allows) };
    },
    go: (name) => { location.hash = '#/' + name; },
    toast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg; t.classList.add('show');
      clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2400);
    },
    async share(text) {
      const full = text + '\n內科晨峰・挑一個比較不塞的時段 → ' + location.href.split('#')[0];
      if (navigator.share) { try { await navigator.share({ title: 'Traffic Gem', text: full }); return; } catch (e) { if (e.name === 'AbortError') return; } }
      try { await navigator.clipboard.writeText(full); app.toast('已複製，貼到 LINE 就能分享'); }
      catch (e) { prompt('複製這段文字分享', full); }
    },
    saveCard(text, sim) {
      // Draws the share card (1200×630) onto a canvas and downloads it as PNG.
      const W = 1200, H = 630, c = document.createElement('canvas'); c.width = W; c.height = H;
      const g = c.getContext('2d');
      const bg = g.createRadialGradient(W, H, 0, W, H, W * 1.1);
      bg.addColorStop(0, '#F6B07E'); bg.addColorStop(0.45, '#F7C9A6'); bg.addColorStop(1, '#FDF1E8');
      g.fillStyle = bg; g.fillRect(0, 0, W, H);
      g.fillStyle = '#D2532A'; g.font = "800 60px Grandstander, 'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif"; g.fillText('Traffic Gem', 56, 110);
      if (sim) { g.fillStyle = '#7A5200'; g.font = "500 30px 'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif"; g.textAlign = 'right'; g.fillText('含模擬資料', W - 56, 100); g.textAlign = 'left'; }
      g.fillStyle = '#5A2410'; g.font = "900 46px 'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif";
      let line = '', y = 260;
      for (const ch of text) {
        if (g.measureText(line + ch).width > W - 112) { g.fillText(line, 56, y); line = ''; y += 74; }
        line += ch;
      }
      g.fillText(line, 56, y);
      g.fillStyle = '#6B3A20'; g.font = "400 28px 'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif"; g.fillText('內科晨峰・挑一個比較不塞的時段 →', 56, H - 56);
      c.toBlob((blob) => {
        const a = document.createElement('a');
        a.download = 'traffic-gem.png';
        a.href = URL.createObjectURL(blob);
        a.click();
        URL.revokeObjectURL(a.href);
        app.toast('已存成圖片');
      }, 'image/png');
    }
  };
  window.app = app;

  // ---------- component base ----------
  class DCLogic {
    constructor() { this.state = {}; }
    setState(patch) {
      this.state = { ...this.state, ...(typeof patch === 'function' ? patch(this.state) : patch) };
      if (this._render) this._render();
    }
    renderVals() { return {}; }
  }

  // ---------- template evaluation ----------
  const EXPR = /\{\{\s*([^}]+?)\s*\}\}/g;
  const ONLY = /^\s*\{\{\s*([^}]+?)\s*\}\}\s*$/;
  function evaluate(expr, scope) {
    if (expr === 'true') return true;
    if (expr === 'false') return false;
    let v = scope;
    for (const k of expr.split('.')) { if (v == null) return undefined; v = v[k]; }
    return v;
  }
  const interp = (s, scope) => s.replace(EXPR, (_, e) => { const v = evaluate(e, scope); return v == null ? '' : String(v); });

  function build(nodes, scope, out) {
    for (const n of nodes) {
      if (n.nodeType === 3) { out.push(document.createTextNode(interp(n.data, scope))); continue; }
      if (n.nodeType !== 1) continue;
      const tag = n.localName;
      if (tag === 'sc-for') {
        const list = evaluate(n.getAttribute('list').match(ONLY)[1], scope) || [];
        const as = n.getAttribute('as');
        list.forEach((item) => build(n.childNodes, { ...scope, [as]: item }, out));
        continue;
      }
      if (tag === 'sc-if') {
        if (evaluate(n.getAttribute('value').match(ONLY)[1], scope)) build(n.childNodes, scope, out);
        continue;
      }
      const el = document.createElementNS(n.namespaceURI, n.localName);
      el._h = {};
      for (const { name, value } of Array.from(n.attributes)) {
        const only = value.match(ONLY);
        if (name.startsWith('on') && only) { el._h[name.slice(2)] = evaluate(only[1], scope); continue; }
        if (only) {
          const v = evaluate(only[1], scope);
          if (v === false || v == null) continue;
          el.setAttribute(name, v === true ? '' : String(v));
        } else {
          el.setAttribute(name, interp(value, scope));
        }
      }
      const kids = [];
      build(n.localName === 'template' ? n.content.childNodes : n.childNodes, scope, kids);
      kids.forEach((k) => el.appendChild(k));
      out.push(el);
    }
    return out;
  }

  // ---------- DOM patching (keeps sliders/focus alive while state changes) ----------
  function patchChildren(parent, next) {
    const prev = Array.from(parent.childNodes);
    next.forEach((nn, i) => {
      const old = prev[i];
      if (!old) { parent.appendChild(nn); return; }
      if (old.nodeType !== nn.nodeType || (nn.nodeType === 1 && old.localName !== nn.localName)) { parent.replaceChild(nn, old); return; }
      if (nn.nodeType === 3) { if (old.data !== nn.data) old.data = nn.data; return; }
      for (const a of Array.from(old.attributes)) if (!nn.hasAttribute(a.name)) old.removeAttribute(a.name);
      for (const a of Array.from(nn.attributes)) if (old.getAttribute(a.name) !== a.value) old.setAttribute(a.name, a.value);
      old._h = nn._h;
      if (old.localName === 'input' && nn.hasAttribute('value') && old.value !== nn.getAttribute('value')) old.value = nn.getAttribute('value');
      patchChildren(old, Array.from(nn.childNodes));
    });
    for (let i = next.length; i < prev.length; i++) prev[i].remove();
  }

  // ---------- screens ----------
  const parsed = {};
  function parse(name) {
    if (parsed[name]) return parsed[name];
    const doc = new DOMParser().parseFromString(SCREENS[name], 'text/html');
    const dc = doc.querySelector('x-dc');
    const helmet = dc.querySelector('helmet');
    const css = Array.from(helmet.querySelectorAll('style')).map((s) => s.textContent).join('\n');
    helmet.remove();
    const tpl = document.createElement('template');
    tpl.innerHTML = dc.innerHTML;
    const src = doc.querySelector('script[data-dc-script]').textContent;
    const Component = new Function('DCLogic', 'app', 'D', '"use strict";\n' + src + '\nreturn Component;')(DCLogic, app, D);
    const title = (doc.querySelector('title') || {}).textContent || 'Traffic Gem';
    return (parsed[name] = { css, tpl, Component, title });
  }

  const stage = document.getElementById('stage');
  const styleEl = document.getElementById('screen-style');
  let current = null;

  // 契約錯誤：缺 label 或 sim 時直接指出是哪個欄位，不預設成真實（CLAUDE.md 硬規則）
  function contractBanner() {
    if (!D.errors.length) return null;
    const box = document.createElement('div');
    box.className = 'contract-error';
    box.setAttribute('role', 'alert');
    const shown = D.errors.slice(0, 5);
    box.textContent = `資料契約錯誤（${D.errors.length} 項，顯示前 ${shown.length} 項）：` + shown.join('；');
    return box;
  }

  function mount(name) {
    if (!SCREENS[name]) name = HOME;
    if (current) {
      current.inst.componentWillUnmount && current.inst.componentWillUnmount();
      current.inst._render = null;
      current.offLive && current.offLive();
    }
    const { css, tpl, Component, title } = parse(name);
    styleEl.textContent = css;
    document.title = title;
    const inst = new Component();
    const banner = contractBanner();
    const render = () => {
      const next = build(tpl.content.childNodes, inst.renderVals() || {}, []);
      if (banner) next.unshift(banner);
      patchChildren(stage, next);
    };
    stage.textContent = '';
    render();
    inst._render = render;
    // 畫面宣告 usesLive 就在即時資料更新時重畫（其他畫面不受影響）
    const offLive = inst.usesLive ? D.onLive(() => inst._render && inst._render()) : null;
    current = { name, inst, offLive };
    window.scrollTo(0, 0);
    inst.componentDidMount && inst.componentDidMount();
  }

  // ---------- events ----------
  function handler(target, type) {
    for (let el = target; el && el !== stage; el = el.parentNode) {
      if (el._h && el._h[type]) return { el, fn: el._h[type] };
    }
    return null;
  }
  stage.addEventListener('click', (ev) => {
    const h = handler(ev.target, 'click');
    if (h) { if (!h.el.disabled) h.fn(ev); return; }
    const a = ev.target.closest('a[href]');
    if (!a) return;
    const href = a.getAttribute('href');
    if (href === '#back') { ev.preventDefault(); history.length > 1 ? history.back() : app.go('Today'); return; }
    const m = href.match(/^([A-Za-z]+)\.dc\.html$/);
    if (m) { ev.preventDefault(); app.go(m[1]); }
  });
  stage.addEventListener('input', (ev) => { const h = handler(ev.target, 'change'); if (h) h.fn(ev); });

  // ---------- routing + fit to phone width ----------
  const route = () => mount(decodeURIComponent(location.hash.replace(/^#\/?/, '')) || HOME);
  // Screens are designed at 390px wide; narrower phones scale down, wider ones get a fluid layout.
  const fit = () => {
    const z = Math.min(1, window.innerWidth / 390);
    const root = document.documentElement;
    root.style.zoom = z === 1 ? '' : z;
    root.style.setProperty('--app-h', (window.innerHeight / z) + 'px');
  };
  // ?topic=<id> 放在 search、路由放在 hash，所以換頁時題目會自動跟著走
  window.addEventListener('hashchange', route);
  window.addEventListener('resize', fit);
  fit();
  route();
  D.startLive(); // 即時路況：先抓一次，之後每 5 分鐘一次
})();
