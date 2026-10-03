"""A fixed battery of score_box inputs. scripts/make_golden_en_score.py recorded score_box's output on it at the
commit before the i18n refactor (tests/fixtures/golden_en_score.json); tests/test_golden_en.py replays it."""
import itertools
from datetime import date, timedelta

from dbw.climatology import Pctl
from dbw.score import DayStat, Level, Sentinel, Sst

DAY = date(2026, 8, 20)
P = Pctl(n=100, p50=1.0, p75=1.5, p90=2.0, p97=2.5)
P_WIDE = Pctl(n=37, p50=0.2, p75=0.5, p90=1.0, p97=1.5)


def ds(offset, median, valid=10, total=10, p90=None):
    return DayStat(DAY - timedelta(days=offset), valid, total, median, p90 if p90 is not None else median)


SERIES = {
    "none": [], "stale": [ds(6, 0.5)], "lowcov": [ds(0, 0.5, valid=1, total=20)], "allnan": [DayStat(DAY, 0, 20, None, None)],
    "calm": [ds(k, 0.5) for k in range(4)], "p75": [ds(k, 1.7) for k in range(4)], "p90": [ds(k, 2.2) for k in range(4)],
    "p97": [ds(k, 2.7) for k in range(4)], "red": [ds(k, 3.4) for k in range(4)], "spike": [ds(1, 1.0), ds(0, 9.0)],
    "spike2": [ds(1, 9.0), ds(0, 9.0)], "rising": [ds(2, 1.55), ds(1, 1.7), ds(0, 1.85)], "old": [ds(2, 0.5, valid=6, total=8)],
    "patchy_rise": [ds(2, 1.55, p90=2.5), ds(1, 1.7, p90=2.5), ds(0, 1.85, p90=2.5)],
    "patchy": [ds(0, 1.0, p90=2.5)], "local": [ds(0, 1.0, p90=1.2)], "gap": [ds(1, 2.7), DayStat(DAY, 0, 10, None, None)],
    "far_prev": [ds(4, 1.0), ds(0, 9.0)],
}
PCTLS = {"std": P, "wide": P_WIDE, "none": None}
SENTINELS = {
    "no": (), "high": (Sentinel("port_said", 9.0, 5.0, DAY),), "calm": (Sentinel("port_said", 2.0, 5.0, DAY),),
    "mild": (Sentinel("port_said", 5.5, 5.0, DAY),), "nodata": (Sentinel("el_arish", None, None, None),),
    "two": (Sentinel("port_said", 9.0, 5.0, DAY), Sentinel("el_arish", 1.2, 4.0, DAY)),
}
SSTS = {"none": None, "warm": Sst(28.5, 27.0), "mild": Sst(27.2, 27.0), "cool": Sst(22.0, 19.0), "nonormal": Sst(25.0, None),
        "nodata": Sst(None, None)}
SHARED = {"no": (), "one": ("sorek_b",), "two": ("sorek_b", "palmachim")}
PREV = {"none": None, "green": Level.GREEN, "orange": Level.ORANGE}


def scenarios():
    """(key, score_box kwargs) over the cross product of a few axes; every reason path is reached at least once."""
    for s, p, se, ss, sh, pv in itertools.product(SERIES, PCTLS, SENTINELS, SSTS, SHARED, PREV):
        # the full product is ~25k cases; thin it deterministically but keep every axis value in play
        if (hash_key := (list(SERIES).index(s) * 7 + list(PCTLS).index(p) * 5 + list(SENTINELS).index(se) * 3
                         + list(SSTS).index(ss) * 2 + list(SHARED).index(sh) + list(PREV).index(pv))) % 16:
            continue
        yield f"{s}|{p}|{se}|{ss}|{sh}|{pv}", dict(day=DAY, series=SERIES[s], pctl=PCTLS[p], sentinels=SENTINELS[se],
                                                      sst=SSTS[ss], prev_level=PREV[pv], shared_with=SHARED[sh])
