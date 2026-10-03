"""Writes tests/fixtures/readable_db.json for tests/test_readable.py: two real slices of the history database
(the 2026-10-02 source switch at ashdod, and the 2026-09-29 four-plant day). Run from a worktree that has a full
data/dbw.sqlite. It does not write any report text: the tests render from the slice."""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from make_golden_en import FIX, load, subset  # noqa: E402

from dbw import registry, report, store  # noqa: E402

CASES = {  # name: (report date, plants, extra boxes the plants share cells with)
    "switch": (date(2026, 10, 2), ["ashdod", "eilat"], []),
    "four": (date(2026, 9, 29), ["hadera", "eilat", "ashkelon", "sorek_a"], ["sorek_b", "palmachim"]),
}


def main():
    boxes = registry.load()
    by_id = {b.id: b for b in boxes}
    full = store.connect()
    out = {}
    for name, (day, plants, extra) in CASES.items():
        ids = set(plants) | set(extra) | {s for p in plants for s in by_id[p].sentinels}
        out[name] = {"date": day.isoformat(), "plants": plants, **subset(full, ids, day)}
        tmp = store.connect(Path(tempfile.mkdtemp()) / "r.sqlite")
        load(tmp, out[name])
        a = report.build_report(full, boxes, plants, day)
        b = report.build_report(tmp, boxes, plants, day)
        if report.render_markdown(a) != report.render_markdown(b):
            sys.exit(f"{name}: slice renders differently from the full database")
        print(name, day, [(p.id, p.level.name, p.source) for p in b.plants], b.changes)
    (FIX / "readable_db.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
