#!/usr/bin/env python3
"""Validate plants.yaml (stdlib + PyYAML).

Fails (exit 1) when:
  * a non-null plant field has no public URL in that plant's `sources` map,
  * an intake_box / sentinel box is not a closed polygon of [lat, lon] points,
  * a polygon point lies outside the sea-plausible lat/lon window of its sea,
  * a sentinel has no box (or no location / source),
  * an `estimated` box has no written reasoning.

Usage: python3 scripts/check_registry.py [path/to/plants.yaml]
"""
import sys
from pathlib import Path

import yaml

# (lat_min, lat_max, lon_min, lon_max) windows that contain open water only
# plausibly reachable by the intakes: E. Mediterranean off Israel/Sinai/Nile
# delta, and the Gulf of Aqaba.
SEA_WINDOWS = {
    "mediterranean": (30.9, 33.5, 31.5, 35.2),
    "red_sea": (27.5, 29.6, 34.0, 35.1),
}
BASES = {"published", "derived", "estimated"}
PLANT_FIELDS = ["name", "sea", "onshore", "intake_box", "intake_depth_m",
                "intake_distance_m", "pretreatment", "capacity", "status"]
PLANT_KEYS = PLANT_FIELDS + ["intake_box_basis", "intake_box_reasoning",
                             "sentinels", "sources"]
SENTINEL_FIELDS = ["name", "sea", "location", "box"]


def is_url(v):
    return isinstance(v, str) and v.startswith(("http://", "https://"))


def has_source(srcs, field):
    v = srcs.get(field)
    if is_url(v):
        return True
    return isinstance(v, list) and bool(v) and all(is_url(x) for x in v)


def check_polygon(label, poly, sea, errs):
    if not isinstance(poly, list) or len(poly) < 4:
        errs.append(f"{label}: polygon needs >= 4 [lat, lon] points (closed ring)")
        return
    if any(not (isinstance(p, list) and len(p) == 2
                and all(isinstance(x, (int, float)) for x in p)) for p in poly):
        errs.append(f"{label}: every polygon point must be [lat, lon] numbers")
        return
    if poly[0] != poly[-1]:
        errs.append(f"{label}: polygon not closed (first point != last point)")
    win = SEA_WINDOWS.get(sea)
    if win is None:
        errs.append(f"{label}: sea {sea!r} not one of {sorted(SEA_WINDOWS)}")
        return
    for lat, lon in poly:
        if not (win[0] <= lat <= win[1] and win[2] <= lon <= win[3]):
            errs.append(f"{label}: point [{lat}, {lon}] outside {sea} window "
                        f"lat {win[0]}-{win[1]} lon {win[2]}-{win[3]}")


def check_latlon(label, v, sea, errs):
    if not (isinstance(v, dict) and isinstance(v.get("lat"), (int, float))
            and isinstance(v.get("lon"), (int, float))):
        errs.append(f"{label}: needs numeric lat and lon")
        return
    win = SEA_WINDOWS.get(sea)
    if win and not (win[0] - 0.5 <= v["lat"] <= win[1] + 0.5
                    and win[2] - 0.5 <= v["lon"] <= win[3] + 0.5):
        errs.append(f"{label}: lat/lon {v['lat']},{v['lon']} implausible for {sea}")


def check_plant(pid, p, sentinel_ids, errs):
    L = f"plants.{pid}"
    for k in PLANT_KEYS:
        if k not in p:
            errs.append(f"{L}: missing key {k} (use null if no public source)")
    srcs = p.get("sources") or {}
    if not isinstance(srcs, dict):
        errs.append(f"{L}.sources must be a map field -> URL")
        srcs = {}
    for f in PLANT_FIELDS:
        if p.get(f) is not None and not has_source(srcs, f):
            errs.append(f"{L}.{f}: non-null but no public URL in sources.{f}")
    for f in srcs:
        if f not in PLANT_FIELDS:
            errs.append(f"{L}.sources.{f}: not a plant field")
    sea = p.get("sea")
    if p.get("onshore") is not None:
        check_latlon(f"{L}.onshore", p["onshore"], sea, errs)
    if p.get("intake_box") is not None:
        check_polygon(f"{L}.intake_box", p["intake_box"], sea, errs)
        basis = p.get("intake_box_basis")
        if basis not in BASES:
            errs.append(f"{L}.intake_box_basis must be one of {sorted(BASES)}")
        if basis == "estimated" and not p.get("intake_box_reasoning"):
            errs.append(f"{L}: estimated box needs intake_box_reasoning")
    if p.get("pretreatment") not in (None, "DAF", "UF", "MMF"):
        errs.append(f"{L}.pretreatment must be DAF | UF | MMF | null")
    for s in p.get("sentinels") or []:
        if s not in sentinel_ids:
            errs.append(f"{L}.sentinels: unknown sentinel id {s}")


def check_sentinel(sid, s, errs):
    L = f"sentinels.{sid}"
    for k in SENTINEL_FIELDS + ["sources"]:
        if not s.get(k):
            errs.append(f"{L}: missing {k} (sentinel needs location + box + source)")
    srcs = s.get("sources") or {}
    for f in SENTINEL_FIELDS:
        if s.get(f) and not has_source(srcs, f):
            errs.append(f"{L}.{f}: no public URL in sources.{f}")
    if s.get("location"):
        check_latlon(f"{L}.location", s["location"], s.get("sea"), errs)
    if s.get("box"):
        check_polygon(f"{L}.box", s["box"], s.get("sea"), errs)


def main(argv):
    path = Path(argv[1] if len(argv) > 1 else "plants.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    errs = []
    plants, sentinels = data.get("plants") or {}, data.get("sentinels") or {}
    if not plants:
        errs.append("no plants")
    for sid, s in sentinels.items():
        check_sentinel(sid, s, errs)
    for pid, p in plants.items():
        check_plant(pid, p, set(sentinels), errs)
    if errs:
        print(f"FAIL {path}: {len(errs)} problem(s)")
        for e in errs:
            print("  -", e)
        return 1
    filled = sum(1 for p in plants.values() for f in PLANT_FIELDS if p.get(f) is not None)
    total = len(plants) * len(PLANT_FIELDS)
    print(f"OK {path}: {len(plants)} plants, {len(sentinels)} sentinels, "
          f"{filled}/{total} plant fields filled, {total - filled} null")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
