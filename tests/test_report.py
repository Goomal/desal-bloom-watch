"""report.py: one in-memory report model, three renderers. Offline, synthetic database."""
import io
from datetime import date, timedelta

import pytest

from dbw import climatology as clim
from dbw import registry, report, store
from dbw.assess import DINEOF
from dbw.providers import gibs, noaa_erddap
from dbw.providers.base import BoxStats, NoData
from dbw.score import Level

EVENT = date(2026, 8, 25)
CALM_SENTINELS = ("port_said", "el_arish", "rafah", "tiran", "gulf_mid")


def bs(v, valid=10, total=10):
    return BoxStats(valid, total, v, v, v, v, v)


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    """5 calm summers (1.00-1.19) for every registry box, then the 2026 event days (the 2 newest)."""
    c = store.connect(tmp_path_factory.mktemp("rep") / "t.sqlite")
    boxes = registry.load()
    for b in boxes:
        rows = {date(y, 8, 25) + timedelta(days=k): bs(1.0 + 0.01 * ((k * 7 + y) % 20))
                for y in range(2021, 2026) for k in range(-40, 41)}
        store.write_days(c, DINEOF, b.id, rows)
        clim.build_percentiles(c, DINEOF, b.id, min_n=5)
    event = {  # day-1, day
        "ashkelon": (9.0, 9.0),        # far above its P97 two days running -> red
        "eilat": (1.18, 1.18),         # yellow on its own (>= P90, < P97) ...
        "tiran": (1.0, 2.0),           # ... but its sentinel jumps to >= 1.5 x its own P90 today only
        "hadera": (1.0, 1.0),          # calm -> green
        "sorek_a": (1.0, 1.0), "sorek_b": (1.0, 1.0),
    }
    for box, (a, b) in event.items():
        store.write_days(c, DINEOF, box, {EVENT - timedelta(days=1): bs(a), EVENT: bs(b)})
    store.write_days(c, DINEOF, "palmachim", {EVENT: NoData("all_nan: 0/10 valid", total_count=10)})
    cells = [(31.93, 34.66), (31.93, 34.70)]
    for box in ("sorek_a", "sorek_b"):
        store.put_cells(c, DINEOF, box, cells)
    return c


@pytest.fixture(scope="module")
def rep(conn):
    return report.build_report(conn, registry.load(), ["hadera", "eilat", "ashkelon", "palmachim", "sorek_a", "sorek_b"],
                               EVENT, mode="dineof")


def by_id(rep, pid):
    return next(p for p in rep.plants if p.id == pid)


def test_plants_are_ordered_worst_first(rep):
    levels = [p.level for p in rep.plants]
    assert levels == sorted(levels, reverse=True)
    assert rep.plants[0].id == "ashkelon" and rep.plants[0].level is Level.RED
    assert rep.worst is Level.RED


def test_grey_plant_says_why(rep):
    p = by_id(rep, "palmachim")
    assert p.level is Level.GREY
    assert "no data" in p.grey_why.lower()
    assert p.level.name in report.render_markdown(rep) and p.grey_why in report.render_markdown(rep)


def test_sentinel_lift_is_labelled_in_plain_words(rep):
    p = by_id(rep, "eilat")
    assert p.level is Level.ORANGE and p.own_level is Level.YELLOW
    assert p.label == "ORANGE (upstream signal: tiran ≥ 1.5× P90; eilat itself is yellow)"
    assert p.label in report.render_markdown(rep) and p.label in report.render_html(rep)


def test_plain_levels_carry_no_upstream_label(rep):
    assert by_id(rep, "hadera").label == "GREEN"
    assert by_id(rep, "ashkelon").label == "RED"


def test_shared_cells_flag_survives_into_markdown(rep):
    assert by_id(rep, "sorek_a").shared_with == ["sorek_b"]
    md = report.render_markdown(rep)
    assert "shares the same satellite pixels with sorek_b" in md
    assert by_id(rep, "hadera").shared_with == []


def test_value_is_shown_against_its_seasonal_percentiles(rep):
    p = by_id(rep, "ashkelon")
    assert p.value == 9.0 and p.pctl.p90 > p.pctl.p50 and p.rank == ">=P97"
    md = report.render_markdown(rep)
    assert "P50" in md and "P97" in md and "9" in md


def test_header_has_report_date_and_data_dates_per_source(rep):
    md = report.render_markdown(rep)
    assert "2026-08-25" in md
    assert any(s.id == DINEOF and s.latest == EVENT for s in rep.sources)
    assert "DINEOF" in md


def test_attribution_is_in_every_format(rep):
    attr = noaa_erddap.ATTRIBUTION
    assert attr in report.render_markdown(rep)
    assert attr.replace("&", "&amp;") in report.render_html(rep) or attr in report.render_html(rep)
    fig = report.draw_map(rep)
    assert attr.split(". ")[0] in " ".join(" ".join(t.get_text().split()) for t in fig.texts)
    for text in (report.render_markdown(rep), report.render_html(rep)):
        assert "satellite" in text.lower() and "not" in text.lower()  # disclaimer


def test_html_is_email_safe(rep):
    h = report.render_html(rep, png=b"\x89PNG\r\n\x1a\nx")
    low = h.lower()
    assert "<script" not in low and "<link" not in low and "@import" not in low
    assert "<style" not in low or "src:" not in low  # no @font-face urls
    assert 'src="data:image/png;base64,' in h and 'src="x.png"' not in h


def test_png_is_a_valid_png_of_sane_size(rep, tmp_path):
    out = tmp_path / "m.png"
    report.render_png(rep, out)
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert 20_000 < len(data) < 2_000_000
    from PIL import Image
    w, h = Image.open(io.BytesIO(data)).size
    assert w >= 600 and h >= 400


def test_write_report_names_files_by_date(rep, tmp_path):
    files, notes = report.write_report(rep, tmp_path, ["html", "md", "png"])
    assert sorted(p.name for p in files.values()) == ["dbw-report-2026-08-25.html", "dbw-report-2026-08-25.md",
                                                       "dbw-report-2026-08-25.png"]
    assert 'src="data:image/png;base64,' in files["html"].read_text(encoding="utf-8")  # the map travels inside the html
    assert notes == []


# --- GIBS underlay: off by default, falls back with a reason ------------------------------------

def _png(color=(30, 90, 160), size=(32, 32), noisy=True):
    from PIL import Image
    im = Image.new("RGB", size, color)
    if noisy:
        for x in range(size[0]):
            im.putpixel((x, x % size[1]), (255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_gibs_url_is_wms_130_latlon_order():
    u = gibs.build_url((29.0, 30.0, 34.0, 35.0), date(2026, 9, 29), 600, 500)
    assert "VERSION=1.3.0" in u and "CRS=EPSG:4326" in u and "BBOX=29.0,34.0,30.0,35.0" in u
    assert "TIME=2026-09-29" in u and "WIDTH=600" in u and "HEIGHT=500" in u


def test_gibs_network_failure_falls_back_to_plain_map_with_reason(rep, tmp_path):
    def boom(url, timeout=30):
        raise gibs.FetchError("network: down")
    files, notes = report.write_report(rep, tmp_path, ["png"], basemap="gibs", fetch=boom)
    assert files["png"].read_bytes()[:4] == b"\x89PNG"
    assert len(notes) == 1 and "GIBS" in notes[0] and "plain map" in notes[0] and "network: down" in notes[0]


def test_gibs_empty_image_falls_back_with_reason(rep, tmp_path):
    files, notes = report.write_report(rep, tmp_path, ["png"], basemap="gibs",
                                       fetch=lambda url, timeout=30: _png((255, 255, 255), noisy=False))
    assert files["png"].exists()
    assert len(notes) == 1 and "empty" in notes[0] and "plain map" in notes[0]


def test_gibs_success_uses_underlay_and_prints_its_attribution(rep, tmp_path):
    files, notes = report.write_report(rep, tmp_path, ["png", "md"], basemap="gibs",
                                       fetch=lambda url, timeout=30: _png())
    assert notes == []
    assert gibs.ATTRIBUTION in files["md"].read_text(encoding="utf-8")


def test_default_basemap_never_touches_the_network(rep, tmp_path):
    def forbidden(url, timeout=30):
        raise AssertionError("network used on the default path")
    files, notes = report.write_report(rep, tmp_path, ["png"], fetch=forbidden)
    assert files["png"].exists() and notes == []


def test_shown_percentiles_are_the_ones_the_level_was_scored_against(conn):
    """The scorer ranks a value against the percentile slot of the report day; the report must show that
    same slot, not the slot of the (older) data date, or its numbers disagree with its own reason lines."""
    from dbw import assess
    day = EVENT + timedelta(days=2)
    r = report.build_report(conn, registry.load(), ["hadera"], day, mode="dineof")
    p = r.plants[0]
    a = assess.Assessor(conn, registry.load(), mode="dineof")
    assert p.data_date == EVENT
    assert p.pctl == a.pctl(DINEOF, "hadera", day)
    assert a.pctl(DINEOF, "hadera", day) != a.pctl(DINEOF, "hadera", EVENT)  # the two slots really differ
