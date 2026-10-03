"""Rebuild dbw/data/percentiles.json from the stored NOAA history (see docs/percentile-export.md).

  dbw backfill --from 2020-05-05          # fills data/dbw.sqlite from public NOAA ERDDAP (about an hour)
  .venv/bin/python scripts/export_percentiles.py [--db data/dbw.sqlite]

The percentiles are recomputed from the observations (not copied from the pctl table), for every
registry box and every backfill source. Run when the history has grown enough to matter (yearly)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dbw import pctl_export, registry, store  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=None, help="SQLite file filled by `dbw backfill` (default data/dbw.sqlite)")
    ap.add_argument("--out", default=str(pctl_export.BUNDLED))
    args = ap.parse_args()
    conn = store.connect(args.db)
    data = pctl_export.build(conn, [b.id for b in registry.load()])
    pctl_export.write(args.out, data)
    h = data["header"]
    n = sum(len(v) for v in data["pctl"].values())
    print(f"wrote {args.out}: {n} box/source series, history {h['history']['first']}..{h['history']['last']}, "
          f"{Path(args.out).stat().st_size} bytes")


if __name__ == "__main__":
    main()
