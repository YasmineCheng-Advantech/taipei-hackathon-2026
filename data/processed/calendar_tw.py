"""上班日判斷：排除週末與國定假日（含補假）。分析通勤只看上班日，假日的車流會把尖峰沖淡。

假日表依行政院人事行政總處公布的 115 年（2026）行事曆；2026 起只補假、不補班，所以沒有週末上班日。
資料範圍延伸到其他年份時，要把那一年的假日補進來。
"""
import datetime as dt

HOLIDAYS = {
    dt.date(2026, 9, 25): "中秋節",
    dt.date(2026, 9, 28): "教師節",
    dt.date(2026, 10, 9): "國慶日補假",
    dt.date(2026, 10, 26): "光復節補假",
}


def is_workday(d):
    """d：date 或 datetime。"""
    d = d.date() if isinstance(d, dt.datetime) else d
    return d.weekday() < 5 and d not in HOLIDAYS
