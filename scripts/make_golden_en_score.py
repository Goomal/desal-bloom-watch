"""Records score_box's output (level, reasons, fields) on tests/golden_scenarios.py into
tests/fixtures/golden_en_score.json. Run ONCE at the commit before the i18n refactor; do not re-run afterwards."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "tests")
from golden_scenarios import scenarios  # noqa: E402

from dbw.score import score_box  # noqa: E402


def snap(sc):
    return {"level": int(sc.level), "reasons": [str(r) for r in sc.reasons], "as_of": str(sc.as_of), "value": sc.value,
            "rank": sc.rank, "extent": sc.extent}


out = {key: snap(score_box(**kw)) for key, kw in scenarios()}
Path("tests/fixtures/golden_en_score.json").write_text(json.dumps(out, indent=0, ensure_ascii=False), encoding="utf-8")
print(len(out), "scenarios;", len({r for v in out.values() for r in v["reasons"]}), "distinct reason strings")
