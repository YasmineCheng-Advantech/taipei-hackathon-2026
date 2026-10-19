"""Build entrances.csv (TASKS.md 工項 4) + a detail CSV from Taipei VD static/live XML.

usage: python3 -I build_entrances.py <dl_dir> <out_dir> VDLive.xml [VDLive_2.xml ...]
"""
import csv, sys, os, xml.etree.ElementTree as ET

T = '{http://traffic.transportdata.tw/standard/traffic/schema/}'

# 入口 → (方向, [(VDID, LinkID 往內湖方向)], 機車判定, 缺口標記, 資料來源, 對應依據, 信心)
ENTRANCES = [
    ('內湖路一段', '由大直往東（往內湖）', [('VTXQJ20', '6000910200000A')], None, '無', 'VD',
     '內湖路一段最西端的東向 VD（文湖路至91巷往東），3/3 車道全偵測', '高'),
    ('堤頂大道', '北向（往內科）', [('VPMSV40', '2000700100210A')], None, '無', 'VD',
     '堤頂大道一段 民權東路–舊宗路，北向 4/4 車道；下游另有 VRPSV00、VRHT600 可交叉驗證', '高'),
    ('民權大橋', '往東（往內湖）', [('VQBUL20', '6005320200000A')], None, '位置偏移', 'VD',
     '橋上無 VD；取橋東端民權東路六段東向 4/4 車道，位於堤頂大道路口以東約 500 m，含堤頂轉入車流', '中'),
    ('麥帥二橋', '往內湖', [], None, '缺口', '僅交工處路口調查',
     '唯一的麥帥二橋 VD（V7230E0）只偵測南向（離開內湖，路段名「麥二正氣」），往內湖方向沒有偵測器', '高'),
    ('成美橋', '往北（往內湖）', [('VMLXB00', '6001470000010A')], None, '位置偏移', 'VD',
     '橋上無 VD；取南岸引道向陽路（重陽路–新明路）北向 3/3 車道，約在橋南端', '中'),
    ('環東大道', '往西進城（由國3／南港進入內湖）', [('V6310G0', '2000900100640A')], 'expressway', '無', 'VD',
     '環東大道東端「環東進城 前方」西向 3/3 車道；若入口指的是西端由麥帥一橋進入的出城車流，改用 V6120C0（見說明）', '中'),
    ('國1 內湖交流道', '下匝道（往內湖）', [], 'expressway', '待 TDX', 'TDX',
     '國道 VD 不在臺北市 VD 內；TDX 需金鑰（401），高公局 tisvcloud 從此環境連線逾時', '—'),
    ('康寧路三段', '由汐止往西（往內湖）', [], None, '缺口', '僅交工處路口調查',
     '臺北市 604 支 VD 中沒有康寧路的偵測器；最近的成功路五段 VSHZU60 是另一條路', '高'),
]


def load_live(path):
    root = ET.parse(path).getroot()
    out = {}
    for v in root.iter(T + 'VDLive'):
        vid = v.findtext(T + 'VDID')
        for lf in v.iter(T + 'LinkFlow'):
            tot, spd = {}, []
            for ln in lf.iter(T + 'Lane'):
                spd.append(float(ln.findtext(T + 'Speed')))
                for vh in ln.iter(T + 'Vehicle'):
                    k = vh.findtext(T + 'VehicleType')
                    tot[k] = tot.get(k, 0) + max(0, int(float(vh.findtext(T + 'Volume'))))
            out[(vid, lf.findtext(T + 'LinkID'))] = dict(
                status=v.findtext(T + 'Status'), time=v.findtext(T + 'DataCollectTime'),
                vol=tot, speeds=spd)
    return root.findtext(T + 'UpdateTime'), out


def load_static(path):
    out = {}
    for v in ET.parse(path).getroot().iter(T + 'VD'):
        for l in v.iter(T + 'DetectionLink'):
            out[(v.findtext(T + 'VDID'), l.findtext(T + 'LinkID'))] = dict(
                road=v.findtext(T + 'RoadName'), lon=v.findtext(T + 'PositionLon'),
                lat=v.findtext(T + 'PositionLat'), dir=l.findtext(T + 'RoadDirection'),
                lanes=l.findtext(T + 'LaneNum'), actual=l.findtext(T + 'ActualLaneNum'))
    return out


def main():
    dl, outdir, lives = sys.argv[1], sys.argv[2], sys.argv[3:]
    static = load_static(os.path.join(dl, 'VD.xml'))
    polls = [load_live(os.path.join(dl, p)) for p in lives]
    main_rows, detail = [], []
    for name, d, vds, moto_rule, gap, src, basis, conf in ENTRANCES:
        ids = ';'.join(v for v, _ in vds)
        moto = '—'
        if moto_rule == 'expressway':
            moto = '不適用（快速道路禁行機車）'
        for vid, link in vds:
            s = static[(vid, link)]
            ok, m_total, sample = 0, 0, []
            for upd, live in polls:
                x = live.get((vid, link))
                if x and x['status'] == '0' and any(sp > 0 for sp in x['speeds']):
                    ok += 1
                if x:
                    m_total += x['vol'].get('M', 0)
                    sample.append(f"{x['time'][11:16]} M{x['vol'].get('M',0)}/S{x['vol'].get('S',0)}/L{x['vol'].get('L',0)}/T{x['vol'].get('T',0)}")
            if moto_rule is None:
                moto = '是' if m_total > 0 else '未知（抽樣期間未測到機車）'
            detail.append(dict(入口=name, 方向=d, VD編號=vid, LinkID=link, 道路=s['road'],
                               經度=s['lon'], 緯度=s['lat'], 偵測方向=s['dir'],
                               偵測車道=f"{s['lanes']}/{s['actual']}",
                               即時回傳=f"{ok}/{len(polls)} 次正常", 抽樣=' | '.join(sample),
                               對應依據=basis, 信心=conf))
        if not vds:
            detail.append(dict(入口=name, 方向=d, VD編號='', LinkID='', 道路='', 經度='', 緯度='',
                               偵測方向='', 偵測車道='', 即時回傳='', 抽樣='', 對應依據=basis, 信心=conf))
        main_rows.append({'入口': name, '方向': d, 'VD編號': ids, '是否涵蓋機車': moto,
                          '缺口標記': gap, '資料來源': src})
    os.makedirs(outdir, exist_ok=True)
    for fn, rows in (('entrances.csv', main_rows), ('entrances_detail.csv', detail)):
        with open(os.path.join(outdir, fn), 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print('polls:', [u for u, _ in polls])


if __name__ == '__main__':
    main()
