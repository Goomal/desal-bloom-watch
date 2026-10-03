import pytest

from dbw import registry

BASE = """
plants:
  alpha:
    name: Alpha
    sea: mediterranean
    intake_box: [[32.0, 34.5], [32.0, 34.6], [32.1, 34.6], [32.1, 34.5], [32.0, 34.5]]
    sentinels: [s1]
    pretreatment: DAF
sentinels:
  s1:
    name: S1
    sea: mediterranean
    box: [[31.0, 33.0], [31.0, 33.1], [31.1, 33.1], [31.1, 33.0], [31.0, 33.0]]
"""


def write(tmp_path, base=BASE, local=None):
    (tmp_path / "plants.yaml").write_text(base, encoding="utf-8")
    if local is not None:
        (tmp_path / "plants.local.yaml").write_text(local, encoding="utf-8")
    return tmp_path / "plants.yaml"


def test_flat_box_list_plants_then_sentinels(tmp_path):
    boxes = registry.load(write(tmp_path))
    assert [(b.id, b.kind) for b in boxes] == [("alpha", "plant"), ("s1", "sentinel")]
    assert boxes[0].bbox == (32.0, 32.1, 34.5, 34.6)
    assert boxes[0].is_rectangle and boxes[0].sentinels == ("s1",)
    assert boxes[0].centroid == pytest.approx((32.05, 34.55))


def test_local_override_wins_and_adds(tmp_path):
    local = """
plants:
  alpha:
    intake_box: [[32.0, 34.0], [32.0, 34.2], [32.2, 34.1], [32.0, 34.0]]
  beta:
    sea: mediterranean
    intake_box: [[32.5, 34.5], [32.5, 34.6], [32.6, 34.6], [32.6, 34.5], [32.5, 34.5]]
"""
    boxes = {b.id: b for b in registry.load(write(tmp_path, local=local))}
    assert set(boxes) == {"alpha", "beta", "s1"}
    assert boxes["alpha"].polygon[1] == (32.0, 34.2) and not boxes["alpha"].is_rectangle
    assert boxes["alpha"].sentinels == ("s1",)  # untouched fields survive the merge


def test_plant_without_box_fails_loudly(tmp_path):
    base = BASE.replace("    intake_box: [[32.0, 34.5], [32.0, 34.6], [32.1, 34.6], [32.1, 34.5], [32.0, 34.5]]\n",
                        "    intake_box: null\n")
    with pytest.raises(registry.RegistryError, match="alpha"):
        registry.load(write(tmp_path, base))


def test_null_non_box_field_is_fine(tmp_path):
    base = BASE.replace("pretreatment: DAF", "pretreatment: null")
    assert len(registry.load(write(tmp_path, base))) == 2


def test_real_registry_loads_all_boxes():
    boxes = registry.load()
    assert sum(b.kind == "plant" for b in boxes) == 8
    assert sum(b.kind == "sentinel" for b in boxes) == 5
