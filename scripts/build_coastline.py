"""Cut Natural Earth 10 m land polygons (public domain) down to the two map regions and write
dbw/data/coastline.json. Run by hand when the bundle needs refreshing; not part of the daily path.

  curl -L -o ne_10m_land.geojson \
    https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson
  python3 scripts/build_coastline.py ne_10m_land.geojson

Stdlib only. Each exterior ring is clipped to the region rectangle (Sutherland-Hodgman) and
rounded to 3 decimals (~100 m)."""
import json
import sys
from pathlib import Path

# region id -> (lat_min, lat_max, lon_min, lon_max); wider than any map view (the view adds a label column)
REGIONS = {
    "mediterranean": (30.4, 33.8, 31.5, 37.5),
    "red_sea": (27.0, 30.3, 33.2, 36.8),
}
OUT = Path(__file__).resolve().parent.parent / "dbw" / "data" / "coastline.json"


def _clip_edge(poly, inside, cross):
    out = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]
        if inside(cur):
            if not inside(prev):
                out.append(cross(prev, cur))
            out.append(cur)
        elif inside(prev):
            out.append(cross(prev, cur))
    return out


def clip(ring, lat0, lat1, lon0, lon1):
    """ring: [(lon, lat)] -> clipped ring (maybe empty)."""
    def at_lon(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_lat(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    poly = [tuple(p) for p in ring]
    for inside, cross in ((lambda p: p[0] >= lon0, at_lon(lon0)), (lambda p: p[0] <= lon1, at_lon(lon1)),
                          (lambda p: p[1] >= lat0, at_lat(lat0)), (lambda p: p[1] <= lat1, at_lat(lat1))):
        if not poly:
            break
        poly = _clip_edge(poly, inside, cross)
    return poly


def main(src):
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    out = {"source": "Natural Earth 10m land (public domain), https://www.naturalearthdata.com/",
           "regions": {}}
    for name, (lat0, lat1, lon0, lon1) in REGIONS.items():
        rings = []
        for feat in data["features"]:
            g = feat["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            for poly in polys:
                ring = clip(poly[0], lat0, lat1, lon0, lon1)
                if len(ring) >= 3:
                    rings.append([[round(x, 3), round(y, 3)] for x, y in ring])
        out["regions"][name] = {"bbox": [lat0, lat1, lon0, lon1], "rings": rings}
        print(f"{name}: {len(rings)} rings, {sum(map(len, rings))} points")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv[1])
