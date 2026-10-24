// 即時路況代理：臺北市交工處 VDLive.xml → 只挑 8 個入口的偵測器，回傳小 JSON。
//
// 為什麼要這一支：瀏覽器不能直接抓 VDLive.xml（來源沒有 CORS 標頭），而且原檔 1.7 MB、612 支
// 偵測器，不該讓手機下載。這支在伺服器端抓、篩、換成 JSON（約 1 KB）。
//
// 抓取頻率：靠 Cache-Control 的 s-maxage=300 保證「每 5 分鐘最多一次」（CLAUDE.md 規定不可更頻繁）。
// 不論同時有多少使用者，邊緣快取只會讓一個請求打到交工處。
//
// 車速算法沿用 data/fetch/collect_vd.py 的 parse_taipei()：每個車道的車速依該車道的車輛數加權平均，
// 同一支偵測器有多個 LinkFlow（不同方向）時再加權合併；Status 不是 0 的偵測器視為沒有資料，不猜值。
//
// 一處刻意的不同：**排除車速回報 0 的車道**（歷史管線是 `速度 >= 0`，這裡是 `> 0`）。
// 理由：有車經過卻回報 0 km/h 是量測缺失，不是車停住了。歷史資料是 15 分鐘 × 23 天的平均，
// 這種雜訊會被洗掉；即時只有 1 分鐘的樣本，一個零速車道就會把數字拉到荒謬的值
// （實測 2026-10-24 08:46 週六早上，堤頂大道含零速車道算出 8 km/h，排除後是 45 km/h）。
//
// 相對地，1 分鐘的樣本本來就小，所以一併回報 samples（有有效車速的車輛數）與 low_sample，
// 讓畫面可以在車太少時說「測不準」，而不是給一個看起來精確的數字。

const SOURCE = 'https://tcgbusfs.blob.core.windows.net/blobtisv/VDLive.xml';

// 入口 → 偵測器與「往內湖方向」的 LinkID，出自 data/processed/entrances_detail.csv。
//
// 為什麼要 LinkID：同一支偵測器常同時回報兩個方向（VPMSV40、VQBUL20、VMLXB00 都是），
// 離線管線用 preview_vd.keep() 只留往內湖的那一段。即時端沒有一起篩的話，
// 車流會變成約兩倍、車速是兩個方向的混合平均，和熱力圖的格子不可比。
const DETECTOR = {
  'neihu-rd-1': { vdid: 'VTXQJ20', link: '6000910200000A' },
  'tiding-n': { vdid: 'VPMSV40', link: '2000700100210A' },
  'minquan-br': { vdid: 'VQBUL20', link: '6005320200000A' },
  'chengmei-br': { vdid: 'VMLXB00', link: '6001470000010A' },
  huandong: { vdid: 'V6310G0', link: '2000900100640A' },
};

// 沒有偵測器的入口：留白，不補數字
const GAPS = {
  'macarthur-2': '這個入口沒有偵測器',
  'kangning-3': '這個入口沒有偵測器',
  'nh1-neihu-ic': '國道偵測器需要 TDX 金鑰，目前沒有即時資料',
};

const STALE_AFTER_MS = 15 * 60 * 1000; // 超過 15 分鐘沒更新就標成可能延遲
const UPSTREAM_TIMEOUT_MS = 10000;
const LOW_SAMPLE = 5; // 車速背後不到 5 輛車就標 low_sample，畫面要說「車太少，測不準」

const WANTED = new Set(Object.values(DETECTOR).map((d) => d.vdid));
// VDID → 往內湖方向的 LinkID
const INBOUND = Object.fromEntries(Object.values(DETECTOR).map((d) => [d.vdid, d.link]));

const tag = (xml, name) => {
  const m = xml.match(new RegExp(`<${name}>([^<]*)</${name}>`));
  return m ? m[1] : null;
};
// 以 <Name> 切出每個區塊。<Names> 這類外層標籤不會誤中，因為字面要有結尾的 '>'。
const blocks = (xml, name) => xml.split(`<${name}>`).slice(1).map((s) => s.split(`</${name}>`)[0]);

/**
 * 解析一個 LinkFlow（一個方向）。
 * speed  有效車道的加權平均車速；沒有任何有效車道時為 null
 * volume 這個方向的總車輛數（輛 / 分鐘）
 * samples 車速背後的車輛數（只算有效車道）
 */
function parseLinkFlow(xml) {
  let weighted = 0;
  let samples = 0;
  let volume = 0;
  for (const lane of blocks(xml, 'Lane')) {
    const laneVol = blocks(lane, 'Vehicle')
      .reduce((n, v) => n + Math.max(0, parseFloat(tag(v, 'Volume')) || 0), 0);
    volume += laneVol;
    // Lane 自己的 <Speed> 排在 <Vehicles> 之前，所以第一個就是車道車速
    const laneSpeed = parseFloat(tag(lane, 'Speed'));
    if (laneVol > 0 && Number.isFinite(laneSpeed) && laneSpeed > 0) {
      weighted += laneSpeed * laneVol;
      samples += laneVol;
    }
  }
  return { speed: samples > 0 ? weighted / samples : null, volume, samples };
}

/** 從整份 XML 解析出目標偵測器的即時值。匯出供對帳用。 */
export function parse(xml) {
  const updatedAt = tag(xml, 'UpdateTime');
  const found = {};
  for (const vd of blocks(xml, 'VDLive')) {
    const id = tag(vd, 'VDID');
    if (!id || !WANTED.has(id)) continue;
    const status = tag(vd, 'Status');
    const collectTime = tag(vd, 'DataCollectTime');
    if (status !== '0') {
      found[id] = { status, collectTime, unavailable: true };
      continue;
    }
    let weighted = 0;
    let samples = 0;
    let volume = 0;
    let lanes = 0;
    let matched = 0;
    for (const lf of blocks(vd, 'LinkFlow')) {
      // 只算往內湖方向那一段。不能取「第一個」LinkFlow：實測 VPMSV40 的第一個就是反方向。
      if (tag(lf, 'LinkID') !== INBOUND[id]) continue;
      matched++;
      lanes += blocks(lf, 'Lane').length;
      const flow = parseLinkFlow(lf);
      volume += flow.volume;
      if (flow.speed !== null) {
        weighted += flow.speed * flow.samples;
        samples += flow.samples;
      }
    }
    // 篩不到往內湖的路段就當作沒有資料，不回退到另一個方向、也不當成 0
    if (!matched) {
      found[id] = { status, collectTime, unavailable: true, reason: '這次沒有往內湖方向的讀數' };
      continue;
    }
    found[id] = {
      status,
      collectTime,
      lanes,
      volume,
      samples,
      speed: samples > 0 ? Math.round(weighted / samples) : null,
    };
  }
  return { updatedAt, found };
}

// 模組層節流：同一個 serverless 實例在 TTL 內不重複打上游。
//
// 為什麼不能只靠 CDN 的 s-maxage：CDN 的快取鍵包含 query string，所以 /api/live?x=1、?x=2…
// 每一個都是 cache miss，任何人都能用迴圈把這支函式變成對市府系統的放大器。
// serverless 會有多個實例，這層不保證全域只有一個請求，但能把放大倍數壓下來；
// 真正的上限仍靠 CDN 的 s-maxage，所以兩層都要。
const THROTTLE_MS = 5 * 60 * 1000;
let cached = null; // { at, data }
let inflight = null; // 併發時共用同一個請求，不要各打各的

async function fetchUpstream() {
  if (cached && Date.now() - cached.at < THROTTLE_MS) {
    if (cached.error) throw cached.error;
    return cached.data;
  }
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      const r = await fetch(SOURCE, { signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
      if (!r.ok) throw new Error(`上游回應 ${r.status}`);
      const parsed = parse(await r.text());
      if (!parsed.updatedAt) throw new Error('讀不到 UpdateTime，來源格式可能變了');
      cached = { at: Date.now(), data: parsed };
      return parsed;
    } catch (e) {
      // 失敗也要記進節流，否則上游掛掉時每個請求都會重試，5 分鐘上限等於消失
      cached = { at: Date.now(), error: e };
      throw e;
    }
  })().finally(() => { inflight = null; });
  return inflight;
}

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.setHeader('Allow', 'GET, HEAD');
    return res.status(405).json({ error: '只支援 GET' });
  }

  let updatedAt;
  let found;
  try {
    // query string 一律忽略：這支沒有任何參數，不讓它變成繞過快取的途徑
    ({ updatedAt, found } = await fetchUpstream());
  } catch (e) {
    // 取不到就說取不到，不拿舊值或歷史值假裝是現在。
    // 對外只給固定訊息，上游的原始錯誤只寫 server log（避免洩漏內部資訊）。
    console.error('[live] 取不到上游資料:', e);
    res.setHeader('Cache-Control', 'public, s-maxage=30');
    return res.status(503).json({ error: '暫時取不到即時資料' });
  }

  const entries = {};
  for (const [row, note] of Object.entries(GAPS)) entries[row] = { gap: true, note };
  for (const [row, d] of Object.entries(DETECTOR)) {
    const f = found[d.vdid];
    if (!f || f.unavailable || f.speed === null) {
      entries[row] = {
        unavailable: true,
        detector: d.vdid,
        note: (f && f.reason) || '偵測器目前沒有有效讀數',
      };
      continue;
    }
    entries[row] = {
      speed: f.speed, // km/h
      volume: f.volume, // 輛 / 分鐘（來源本來就是每分鐘）
      samples: f.samples, // 車速背後有幾輛車
      low_sample: f.samples < LOW_SAMPLE, // 車太少，畫面要說「測不準」
      lanes: f.lanes,
      detector: d.vdid,
      link_id: d.link,
      collect_time: f.collectTime,
      label: 'observed', // 真實觀測
      sim: false,
      src: 'vd-live',
    };
  }

  const age = Date.now() - Date.parse(updatedAt);
  res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=600');
  return res.status(200).json({
    updated_at: updatedAt,
    fetched_at: new Date().toISOString(),
    stale: !(age >= 0 && age < STALE_AFTER_MS),
    units: { speed: 'km/h', volume: '輛 / 分鐘' },
    source: { id: 'vd-live', name: '臺北市交工處 VD 即時資料（VDLive.xml）', url: SOURCE },
    entries,
  });
}
