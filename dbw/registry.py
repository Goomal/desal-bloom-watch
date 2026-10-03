"""Load plants.yaml (+ optional plants.local.yaml deep-merged on top) into a flat list of Boxes."""
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "plants.yaml"


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class Box:
    id: str
    kind: str  # "plant" | "sentinel"
    polygon: tuple  # closed ring of (lat, lon)
    sea: str | None = None
    sentinels: tuple = ()  # sentinel ids upstream of this plant
    name: str | None = None  # display name from plants.yaml
    pretreatment: str | None = None  # DAF | UF | MMF | None

    @property
    def bbox(self):
        lats = [p[0] for p in self.polygon]
        lons = [p[1] for p in self.polygon]
        return min(lats), max(lats), min(lons), max(lons)

    @property
    def centroid(self):
        lat0, lat1, lon0, lon1 = self.bbox
        return (lat0 + lat1) / 2, (lon0 + lon1) / 2

    @property
    def is_rectangle(self):
        pts = self.polygon
        return (len(pts) == 5 and len({p[0] for p in pts}) == 2 and len({p[1] for p in pts}) == 2)


def deep_merge(base, over):
    """Dicts merge recursively; any other value in `over` replaces the base value."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base[k], v) if k in base else v
        return out
    return over


def _polygon(label, raw):
    if not raw or len(raw) < 4:
        raise RegistryError(f"{label}: needs a polygon of >= 4 [lat, lon] points")
    return tuple((float(p[0]), float(p[1])) for p in raw)


def load(path=None):
    path = Path(path) if path else DEFAULT_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    local = path.with_name("plants.local.yaml")
    if local.exists():
        data = deep_merge(data, yaml.safe_load(local.read_text(encoding="utf-8")) or {})
    boxes = []
    for pid, p in (data.get("plants") or {}).items():
        boxes.append(Box(pid, "plant", _polygon(f"plant {pid}: intake_box", p.get("intake_box")),
                         p.get("sea"), tuple(p.get("sentinels") or ()), p.get("name"), p.get("pretreatment")))
    for sid, s in (data.get("sentinels") or {}).items():
        boxes.append(Box(sid, "sentinel", _polygon(f"sentinel {sid}: box", s.get("box")), s.get("sea"),
                         name=s.get("name")))
    ids = [b.id for b in boxes]
    if len(ids) != len(set(ids)):
        raise RegistryError("duplicate box id across plants and sentinels")
    if not any(b.kind == "plant" for b in boxes):
        raise RegistryError("registry has no plants")
    return boxes
