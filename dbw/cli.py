"""dbw command line: run, backfill, score, hindcast, report, setup, schedule, telegram, send-test, plants, skill, doctor."""
import argparse
import dataclasses
import json
import shutil
import socket
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dbw import assess, climatology, config, i18n, pctl_export, registry, report, schedule, store
from dbw.channels import telegram
from dbw.providers import build_providers, gibs, noaa_erddap
from dbw.providers.base import BoxStats, FetchError, NoData, UpstreamUnreachable


RECENT_DAYS = 45  # setup with the bundled percentile export fetches this many days back, not the full history
CATCHUP_DAYS = 10  # a daily run (no --date) re-fetches this many days back: a skipped day or a late slice is picked up
CATCHUP_DELAY = 1.0  # seconds between its ERDDAP requests
NETWORK_WAIT = 300  # a scheduled run that fires as the laptop wakes waits up to this many seconds for the network
NETWORK_POLL = 15  # seconds between its DNS checks
_resolve = socket.getaddrinfo
_sleep = time.sleep
TELEGRAM_TEST_TEXT = "Desal Bloom Watch test: the bot can reach this chat."
TELEGRAM_STEPS = """Telegram, three steps (docs/telegram.md):
  1. In Telegram, message @BotFather, send /newbot and answer its questions. It gives you a token.
  2. Put the token in the file .env next to config.yaml, as one line:  DBW_TELEGRAM_TOKEN=<your token>
     Edit that file yourself, in your own editor. Never paste the token into a chat or a command line.
  3. In Telegram, open your new bot and send it any message (press Start)."""


def _root():
    """The repository root, where the scheduled job runs and keeps data/dbw-run.log."""
    return Path(__file__).resolve().parents[1]


def select_boxes(boxes, plant_ids):
    """All boxes, or only the named plants plus the sentinels upstream of them."""
    if not plant_ids:
        return list(boxes)
    plants = {b.id: b for b in boxes if b.kind == "plant"}
    unknown = [p for p in plant_ids if p not in plants]
    if unknown:
        raise SystemExit(f"unknown plant id(s): {', '.join(unknown)} (known: {', '.join(plants)})")
    wanted = set(plant_ids)
    for p in plant_ids:
        wanted.update(plants[p].sentinels)
    return [b for b in boxes if b.id in wanted]


def _token(provider, result):
    label = getattr(provider, "short", provider.source)
    if isinstance(result, BoxStats):
        return f"{label} {result.valid_count}/{result.total_count} mean={result.mean:.3g}"
    return f"{label} no data ({result.reason})"


def run_day(conn, boxes, providers, day, down=None):
    """Fetch every box x provider for `day`, store it, return one summary line per box. A result from an
    unreachable service is not stored (it would overwrite a good row with "no data"); its reason is appended to `down`."""
    lines = []
    for box in boxes:
        tokens = []
        for provider in providers.values():
            result = provider.fetch(box, day)
            if isinstance(result, NoData) and not result.reachable:
                if down is not None:
                    down.append(result.reason)
            else:
                store.write_result(conn, day, provider.source, box.id, result)
            tokens.append(_token(provider, result))
        lines.append(f"{box.id} [{box.kind}] " + " | ".join(tokens))
    return lines


def cmd_run(args):
    if args.log:
        return schedule.run_logged(args.log, lambda: _run(args))
    _run(args)
    return 0


def _catch_up(conn, boxes, day):
    """Fetch the last CATCHUP_DAYS days of the three scored sources with regional range requests, replacing any
    stale "no data" row. Days a dataset does not have yet get no row. -> the reason NOAA was unreachable, or None."""
    try:
        reports = climatology.backfill(conn, boxes, list(climatology.BACKFILL_SOURCES), day - timedelta(days=CATCHUP_DAYS),
                                       day, force=True, delay=CATCHUP_DELAY, log=lambda m: print(m, flush=True))
    except UpstreamUnreachable as e:
        return e.reason
    failed = [f for r in reports.values() for f in r.failed]
    return failed[0].split(": ", 1)[-1] if failed else None


def _wait_for_network():
    """Wait until the ERDDAP host resolves, up to NETWORK_WAIT seconds; print one line if it had to wait."""
    host = urllib.parse.urlsplit(noaa_erddap.BASE).hostname
    waited = 0
    while True:
        try:
            _resolve(host, 443)
        except OSError:
            if waited >= NETWORK_WAIT:
                print(f"network: still down after {waited} s; running with the data already stored", flush=True)
                return
            _sleep(NETWORK_POLL)
            waited += NETWORK_POLL
        else:
            if waited:
                print(f"network: up after {waited} s", flush=True)
            return


def _run(args):
    """One run: fetch (one date, or catch up when there is none), then write the report. -> schedule.OK / PARTIAL."""
    if not args.date and args.sources:
        raise SystemExit("--sources works with --date only")
    day = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    names = [s for s in args.sources.split(",") if s] if args.sources else None
    try:
        providers = build_providers(names)
    except KeyError as e:
        raise SystemExit(f"unknown source {e}")
    cfg = _load_config(args)
    if cfg is None and not args.date and not args.no_report:
        raise SystemExit(f"no {args.config}: run `dbw setup` first")
    plants = _csv(args.plants) or (cfg or {}).get("plants")
    boxes = select_boxes(registry.load(), plants)
    t0 = time.monotonic()
    conn = store.connect()
    down = []
    if args.date:
        for line in run_day(conn, boxes, providers, day, down):
            print(line)
        what = f"{len(boxes)} boxes x {len(providers)} sources for {day}"
    else:
        if args.log:  # the scheduled run
            _wait_for_network()
        reason = _catch_up(conn, boxes, day)
        if reason:
            down.append(reason)
        what = f"{len(boxes)} boxes caught up over {day - timedelta(days=CATCHUP_DAYS)} .. {day}"
    print(f"done: {what}, {store.count(conn)} rows in {store.default_path()}, {time.monotonic() - t0:.1f}s")
    upstream = down[0] if down else None
    if upstream:
        print(f"partial: NOAA data could not be fetched today ({upstream}); the report is built from the data already stored")
    result = schedule.PARTIAL if upstream else schedule.OK
    if args.no_report:
        return result
    if cfg is None:
        print(f"no {args.config}: report not written (run `dbw setup`, or `dbw report --date {day} --out DIR`)")
        return result
    out, formats, basemap = config.report_settings(cfg)
    sending = bool(config.telegram_chat_ids(cfg))
    if sending:  # telegram sends the short message and the HTML file, whichever formats the config lists
        formats = list(dict.fromkeys([*formats, "html", "txt"]))
    _, files = _emit(conn, day, cfg["plants"], out, formats, basemap, args.mode, config.report_language(cfg), upstream=upstream)
    reasons = [schedule.UPSTREAM] if upstream else []
    if sending and not _send_telegram(cfg, args.config, files):
        reasons.append(schedule.TELEGRAM)
    return schedule.partial(*reasons) if reasons else schedule.OK


def _csv(value):
    return [x for x in value.split(",") if x] if value else None


def _load_config(args):
    try:
        return config.load(args.config)
    except config.ConfigError as e:
        raise SystemExit(str(e))


def _emit(conn, day, plants, out, formats, basemap, mode, lang=i18n.DEFAULT, upstream=None):
    """Build and write the report files; print one line per file and any basemap fallback reason. -> (report, files)."""
    rep = report.build_report(conn, registry.load(), plants, day, mode=mode, upstream=upstream)
    files, notes = report.write_report(rep, out, formats, basemap, lang=lang)
    for fmt, path in files.items():
        print(f"report {fmt}: {path} ({path.stat().st_size} bytes)")
    for n in notes:
        print(f"basemap: {n}")
    if basemap == "gibs" and "png" in formats and not notes:
        print(gibs.ATTRIBUTION)
    print(f"levels: {', '.join(f'{p.id} {p.level.name}' for p in rep.plants)}")
    return rep, files


def _write_report(*args, **kwargs):
    _emit(*args, **kwargs)
    return 0


def _telegram_token(config_path):
    """The bot token: the environment, else the .env file that sits next to the config. Raises TelegramError."""
    return telegram.load_token(Path(config_path).resolve().parent / ".env")


def _send_telegram(cfg, config_path, files):
    """Send the short message, then the HTML file, to every configured chat. A failure is one logged line, never an
    exception: the report is already written. -> True when every chat got both."""
    try:
        token = _telegram_token(config_path)
    except telegram.TelegramError as e:
        print(f"telegram: failed: {e}")
        return False
    text = files["txt"].read_text(encoding="utf-8")
    caption = text.splitlines()[0] if text.strip() else ""
    ok = True
    for chat in config.telegram_chat_ids(cfg):
        try:
            telegram.send_report(token, chat, text, files["html"], caption)
        except Exception as e:  # whatever goes wrong here, the report is written: log it (redacted, no traceback)
            print(f"telegram: failed for {chat}: {telegram.redact(e, token)}")
            ok = False
        else:
            print(f"telegram: sent to {chat}")
    return ok


def cmd_report(args):
    day = date.fromisoformat(args.date)
    cfg = _load_config(args)
    plants = _csv(args.plants) or (cfg or {}).get("plants") or [b.id for b in registry.load() if b.kind == "plant"]
    c_out, c_formats, c_basemap = config.report_settings(cfg)
    formats = _csv(args.format) or c_formats
    bad = [f for f in formats if f not in config.FORMATS]
    if bad:
        raise SystemExit(f"unknown format(s): {', '.join(bad)} (use {','.join(config.FORMATS)})")
    try:
        return _write_report(store.connect(), day, plants, args.out or c_out, formats, args.basemap or c_basemap,
                             args.mode, args.language or config.report_language(cfg))
    except ValueError as e:
        raise SystemExit(str(e))


def cmd_setup(args):
    boxes = registry.load()
    path = Path(args.config)
    interactive = not (args.yes or args.no_input)
    if path.exists() and not args.yes:
        raise SystemExit(f"{path} exists; pass --yes to overwrite it")
    plants = _csv(args.plants)
    if not plants:
        if not interactive:
            raise SystemExit("--plants is required without interactive input (e.g. --plants hadera,eilat)")
        print("Which plants do you want a daily report for?")
        plants = config.prompt_plants(boxes)
    out = args.out or config.DEFAULT_OUT
    if not args.out and interactive:
        out = input(f"Output folder for the reports [{config.DEFAULT_OUT}]: ").strip() or config.DEFAULT_OUT
    language = args.language or i18n.DEFAULT
    if not args.language and interactive:
        language = config.prompt_language(input_fn=input)
    try:
        cfg = config.write(path, plants, out, boxes, basemap=args.basemap, language=language)
    except config.ConfigError as e:
        raise SystemExit(str(e))
    print(f"wrote {path}: plants {', '.join(plants)}, reports to {out}, language {language}")
    chosen = select_boxes(boxes, plants)
    conn = store.connect()
    end = datetime.now(timezone.utc).date()
    t0 = time.monotonic()
    if not args.skip_backfill:
        export = None if args.full_history else pctl_export.load()
        if export:
            loaded = pctl_export.install(conn, export, [b.id for b in chosen])
            h = export["header"]
            print(f"loaded seasonal percentiles for {loaded} box/source pairs from the bundled export "
                  f"(NOAA history {h['history']['first']} .. {h['history']['last']}, built {h['built_at']}); "
                  f"pass --full-history to rebuild them from a full backfill instead", flush=True)
            start = end - timedelta(days=RECENT_DAYS)
        else:
            if not args.full_history:
                print("no bundled percentile export found; falling back to the full history backfill")
            start = climatology.FIRST_BACKFILL
        print(f"backfill {start} .. {end} for {', '.join(b.id for b in chosen)} "
              f"(resumable{'' if export else '; the first full run takes about an hour'})", flush=True)
        reports = climatology.backfill(conn, chosen, list(climatology.BACKFILL_SOURCES), start, end,
                                       delay=args.delay, log=lambda m: print(m, flush=True))
        if not export:
            for source in reports:
                for box in chosen:
                    climatology.build_percentiles(conn, source, box.id)
        failed = [f for r in reports.values() for f in r.failed]
        print(f"backfill done in {time.monotonic() - t0:.0f}s, {len(failed)} failed days")
    c_out, formats, basemap = config.report_settings(cfg)
    rc = _write_report(conn, end, plants, c_out, formats, basemap, assess.MODES[0], config.report_language(cfg))
    rc = rc or _offer_schedule(args, interactive, cfg)
    return _offer_telegram(args, interactive) or rc


def _offer_telegram(args, interactive):
    """--telegram sets it up, --no-telegram and --yes do not; interactively ask, default no."""
    want = args.telegram
    if not want and not args.no_telegram and interactive:
        want = input("Send the daily report to Telegram? [y/N] ").strip().lower() in ("y", "yes")
    if not want:
        return 0
    print(TELEGRAM_STEPS)
    if interactive:
        input("Press Enter when the three steps are done. ")
    try:
        _chat_id_step(args.config, write=True, pick=None)
    except SystemExit as e:
        print(f"{e}\ntelegram is not set up yet: fix that, then run `dbw telegram chat-id --write` "
              f"(add `--pick <id>` when it lists several chats); see docs/telegram.md", file=sys.stderr)
        return 1
    return 0


def _offer_schedule(args, interactive, cfg):
    """--schedule installs the daily job, --no-schedule and --yes do not; interactively ask, default yes."""
    want = args.schedule
    if not want and not args.no_schedule and interactive:
        _, time_text = _schedule_choice(args, cfg)
        want = input(f"Run this every day at {time_text}? [Y/n] ").strip().lower() in ("", "y", "yes")
    if not want:
        return 0
    try:
        _install_schedule(args, config.load(args.config))
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1
    return 0


def _schedule_choice(args, cfg):
    """(runner, time) from the flags, else the config, else the platform default and the measured time."""
    cfg = cfg or {}
    try:
        runner = schedule.check_runner(args.runner or cfg.get("runner") or schedule.default_runner())
        time_text = schedule.normalize_time(args.time or (cfg.get("schedule") or {}).get("time") or schedule.default_time())
    except schedule.ScheduleError as e:
        raise SystemExit(str(e))
    return runner, time_text


def _install_schedule(args, cfg, dry_run=False):
    """Install the daily job and record runner and time in the config. Raises SystemExit with the reason."""
    runner, time_text = _schedule_choice(args, cfg)
    root = _root()
    job = schedule.make_job(root, time_text)
    job = dataclasses.replace(job, args=job.args + ["--config", str(Path(args.config).resolve())])
    if not dry_run:
        if not job.exe.exists():
            raise SystemExit(f"{job.exe} not found: make the venv first (python3 -m venv .venv && .venv/bin/pip install .)")
        job.log.parent.mkdir(parents=True, exist_ok=True)
    try:
        lines = schedule.install(runner, job, dry_run=dry_run, tmp=job.log.parent)
        if not dry_run:
            config.set_schedule(args.config, runner, time_text)
    except (schedule.ScheduleError, config.ConfigError) as e:
        raise SystemExit(str(e))
    for line in lines:
        print(line)
    return runner, time_text


def _chat_id_step(config_path, write, pick):
    """List the chats that have messaged the bot; with `write`, add the chosen one to the config. -> exit code."""
    path = Path(config_path)
    if pick is not None and not write:
        raise SystemExit("--pick works with --write only")
    if write and not path.exists():
        raise SystemExit(f"no {path}: run `dbw setup` first")
    try:
        chats = telegram.chats_from_updates(telegram.get_updates(_telegram_token(path)))
    except telegram.TelegramError as e:
        raise SystemExit(str(e))
    if not chats:
        print("No chat has messaged the bot yet: send your bot a message first (open it in Telegram and press Start; "
              "for a group, add the bot and write something there), then run this again. Telegram keeps unread "
              "messages for 24 hours.")
        return 1
    for chat in chats:
        print(f"  {telegram.describe_chat(chat)}")
    if not write:
        print("To save one: dbw telegram chat-id --write   (add --pick <id> when there are several)")
        return 0
    if pick is None:
        if len(chats) > 1:
            raise SystemExit("several chats found: choose one with --pick <id>")
        pick = chats[0]["id"]
    elif str(pick).strip() not in {str(c["id"]) for c in chats}:
        raise SystemExit(f"{pick} is not one of the chats listed above")
    try:
        config.add_telegram_chat(path, pick)
    except (config.ConfigError, ValueError) as e:
        raise SystemExit(str(e))
    print(f"added {pick} to {path}: telegram is on. Check it with `dbw send-test telegram`.")
    return 0


def cmd_telegram(args):
    return _chat_id_step(args.config, args.write, args.pick)


def _latest_report(cfg):
    """(short-message text, html path or None) of the newest dbw-report-<date>.txt in the output folder, or None."""
    out = config.report_settings(cfg)[0]
    txts = sorted(out.glob("dbw-report-*.txt")) if out.is_dir() else []
    if not txts:
        return None
    html = txts[-1].with_suffix(".html")
    return txts[-1].read_text(encoding="utf-8"), html if html.exists() else None


def cmd_send_test(args):
    cfg = _load_config(args)
    chats = config.telegram_chat_ids(cfg)
    if not chats:
        raise SystemExit("telegram is not enabled in config.yaml: run `dbw telegram chat-id --write` first (docs/telegram.md)")
    try:
        token = _telegram_token(args.config)
    except telegram.TelegramError as e:
        raise SystemExit(str(e))
    latest = _latest_report(cfg) if args.latest else None
    if args.latest and not latest:
        print(f"no report found in {config.report_settings(cfg)[0]}: sending only the test message")
    failed = 0
    for chat in chats:
        try:
            telegram.send_message(token, chat, TELEGRAM_TEST_TEXT)
            if latest:
                text, html = latest
                telegram.send_report(token, chat, text, html, text.splitlines()[0] if text.strip() else "")
        except telegram.TelegramError as e:
            print(f"chat {chat}: {e}")
            failed += 1
        else:
            print(f"chat {chat}: ok")
    return 1 if failed else 0


def cmd_schedule(args):
    path = Path(args.config)
    if args.action == "install":
        dry = args.dry_run
        cfg = None
        if path.exists():
            cfg = _load_config(args)
        elif not dry:
            raise SystemExit(f"no {path}: run `dbw setup` first (the daily job needs a config to write reports)")
        _install_schedule(args, cfg, dry)
        return 0
    cfg = _load_config(args) if path.exists() else None
    runner, _ = _schedule_choice(args, cfg)
    try:
        if args.action == "remove":
            for line in schedule.remove(runner):
                print(line)
            return 0
        st = schedule.status(runner)
    except schedule.ScheduleError as e:
        raise SystemExit(str(e))
    log = schedule.make_job(_root(), "00:00").log
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    for line in schedule.render_status(st, text, log):
        print(line)
    return 0


def plant_groups(boxes):
    """[(sea, [{id, name, lat}])]: plants only, seas alphabetical, each sea north to south."""
    seas = {}
    for b in boxes:
        if b.kind == "plant":
            lat = round(sum(p[0] for p in b.polygon) / len(b.polygon), 2)
            seas.setdefault(b.sea or "", []).append({"id": b.id, "name": b.name or b.id, "lat": lat})
    return [(sea, sorted(ps, key=lambda p: -p["lat"])) for sea, ps in sorted(seas.items())]


def cmd_plants(args):
    groups = plant_groups(registry.load())
    if args.json:
        print(json.dumps([{"sea": sea, "plants": ps} for sea, ps in groups], ensure_ascii=False, indent=1))
        return 0
    for sea, ps in groups:
        print(sea)
        for p in ps:
            print(f"  {p['id']:<16} {p['name']}  ({p['lat']}N)")
    return 0


SKILL_NAME = "desal-bloom-watch"


def _skill_targets(args):
    base = Path.cwd() if args.project else Path.home()
    out = []
    if args.claude or not args.codex:
        out.append(base / ".claude" / "skills" / SKILL_NAME)
    if args.codex:
        out.append(base / ".agents" / "skills" / SKILL_NAME)
    return out


def cmd_skill(args):
    """Copy skill/ (a real copy, no links: it works on Windows too) to where Claude Code and/or Codex load skills."""
    targets = _skill_targets(args)
    taken = [t for t in targets if t.exists() or t.is_symlink()]
    if taken and not args.force:
        print("already there, nothing changed (use --force to replace): " + ", ".join(str(t) for t in taken), file=sys.stderr)
        return 1
    for t in targets:
        if t.is_symlink():
            t.unlink()
        elif t.exists():
            shutil.rmtree(t)
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(_root() / "skill", t)
        print(f"installed the skill to {t}")
    print("start a new Claude Code / Codex session to load it; re-run with --force after `git pull`")
    return 0


def cmd_backfill(args):
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date()
    sources = _csv(args.sources) or list(climatology.BACKFILL_SOURCES)
    unknown = [s for s in sources if s not in climatology.noaa_erddap.SOURCES]
    if unknown:
        raise SystemExit(f"unknown source(s): {', '.join(unknown)}")
    boxes = registry.load()
    if args.boxes:
        wanted = _csv(args.boxes)
        missing = [w for w in wanted if w not in {b.id for b in boxes}]
        if missing:
            raise SystemExit(f"unknown box id(s): {', '.join(missing)}")
        boxes = [b for b in boxes if b.id in wanted]
    conn = store.connect()
    reports = climatology.backfill(conn, boxes, sources, start, end, force=args.force, delay=args.delay,
                                   log=lambda m: print(m, flush=True))
    for source, rep in reports.items():
        rows = conn.execute("SELECT COUNT(*) FROM obs WHERE source=?", (source,)).fetchone()[0]
        print(f"{source}: {rep.requests} requests, {rep.days_written} (date,box) results written, "
              f"{rep.skipped_chunks} chunks skipped, {len(rep.failed)} failed days, {rows} obs rows total, "
              f"{rep.seconds:.0f}s")
        for f in rep.failed:
            print(f"  FAILED {f}")
        for box in boxes:
            climatology.build_percentiles(conn, source, box.id)
    print(f"percentiles rebuilt for {len(boxes)} boxes x {len(reports)} sources")
    return 1 if any(r.failed for r in reports.values()) else 0


def _assessor(args, leave_out):
    boxes = registry.load()
    return boxes, assess.Assessor(store.connect(), boxes, mode=args.mode, leave_out=leave_out)


def _plant_ids(boxes, arg):
    plants = [b.id for b in boxes if b.kind == "plant"]
    wanted = _csv(arg) or plants
    unknown = [p for p in wanted if p not in plants]
    if unknown:
        raise SystemExit(f"unknown plant id(s): {', '.join(unknown)} (known: {', '.join(plants)})")
    return wanted


def cmd_score(args):
    day = date.fromisoformat(args.date)
    boxes, a = _assessor(args, leave_out=False)
    for pid in _plant_ids(boxes, args.plants):
        sc = a.assess(pid, day, prev_level=a.assess(pid, day - timedelta(days=1)).level)
        print(f"{pid}: {sc.level.name}")
        for r in sc.reasons:
            print(f"  - {r}")
    return 0


def cmd_hindcast(args):
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    boxes, a = _assessor(args, leave_out=True)
    grid = {pid: a.assess_range(pid, start, end) for pid in _plant_ids(boxes, args.plants)}
    print(assess.render_grid(grid))
    print("G green  Y yellow  O orange  R red  . grey (no usable data)")
    before = date.fromisoformat(args.before)
    ok, facts = assess.hindcast_verdict(grid, before)
    for f in facts:
        print(f)
    print(f"HINDCAST {'PASS' if ok else 'FAIL'}")
    orig, _ = assess.plan_clause_verdict(grid, before)
    print(f"(original PLAN section 4 clause: {'PASS' if orig else 'FAIL'}; see docs/scoring.md)")
    return 0 if ok else 1


def cmd_doctor(args):
    ok = True

    def report(good, text):
        nonlocal ok
        ok = ok and good
        print(f"{'OK  ' if good else 'FAIL'} {text}")

    boxes = []
    try:
        boxes = registry.load()
        report(True, f"registry: {len(boxes)} boxes")
    except Exception as e:  # report any load failure, not just RegistryError
        report(False, f"registry: {e}")
    try:
        conn = store.connect()
        conn.execute("INSERT INTO obs(date, source, box, stat, value, fetched_at)"
                     " VALUES ('0000-00-00','doctor','doctor','probe',0,'')")
        conn.rollback()
        report(True, f"db writable: {store.default_path()}")
    except Exception as e:
        report(False, f"db: {e}")
    if boxes:
        probe = next(b for b in boxes if b.kind == "plant")
        day = datetime.now(timezone.utc).date() - timedelta(days=5)
        for name, provider in build_providers().items():
            r = provider.fetch(probe, day)
            if isinstance(r, NoData) and not r.reachable:
                report(False, f"{name} {day}: unreachable ({r.reason})")
            else:
                report(True, f"{name} {day}: reachable ({'data' if isinstance(r, BoxStats) else r.reason})")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dbw", description="Desal Bloom Watch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch and store, then write the report (no --date: today, catching up the last days)")
    r.add_argument("--date", help="YYYY-MM-DD (default: today UTC, with a catch-up of the last days)")
    r.add_argument("--log", help="append output and a RESULT line to this file (the scheduled job uses data/dbw-run.log)")
    r.add_argument("--plants", help="comma-separated plant ids (their sentinels come along)")
    r.add_argument("--sources", help="comma-separated source names (default: all)")
    r.add_argument("--config", default=str(config.DEFAULT_PATH), help="config.yaml: plants and report output (default ./config.yaml)")
    r.add_argument("--no-report", action="store_true", help="fetch and store only; do not write the report")
    r.add_argument("--mode", choices=assess.MODES, default=assess.MODES[0], help="chlorophyll source rule for the report")
    r.set_defaults(func=cmd_run)
    b = sub.add_parser("backfill", help="fill history from ERDDAP range queries, then rebuild percentiles")
    b.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    b.add_argument("--to", dest="end", help="YYYY-MM-DD (default: today UTC; the latest slice is used)")
    b.add_argument("--sources", help="comma-separated ERDDAP dataset ids (default: DINEOF, N20 chl, CoralTemp SST)")
    b.add_argument("--boxes", help="comma-separated box ids (default: every plant and sentinel)")
    b.add_argument("--force", action="store_true", help="re-request covered windows and overwrite existing rows")
    b.add_argument("--delay", type=float, default=1.0, help="seconds to sleep between requests (default 1)")
    b.set_defaults(func=cmd_backfill)
    for name, fn, helptext in (("score", cmd_score, "score every plant for one date (needs backfilled history)"),
                               ("hindcast", cmd_hindcast, "plant x day level grid, each year scored without itself")):
        sp = sub.add_parser(name, help=helptext)
        if name == "score":
            sp.add_argument("--date", required=True, help="YYYY-MM-DD")
        else:
            sp.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
            sp.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
            sp.add_argument("--before", default=assess.CORE_BEFORE, help="PASS needs orange+ before this date")
        sp.add_argument("--plants", help="comma-separated plant ids (default: all)")
        sp.add_argument("--mode", choices=assess.MODES, default=assess.MODES[0], help="chlorophyll source rule")
        sp.set_defaults(func=fn)
    rp = sub.add_parser("report", help="write the report (html, markdown, PNG map, short text) for one date from the stored history")
    rp.add_argument("--date", required=True, help="YYYY-MM-DD")
    rp.add_argument("--plants", help="comma-separated plant ids (default: config.yaml, else every plant)")
    rp.add_argument("--format", help=f"comma-separated: {','.join(config.FORMATS)} (default: config.yaml, else all)")
    rp.add_argument("--out", help="output folder (default: config.yaml, else ./reports)")
    rp.add_argument("--language", choices=i18n.LANGUAGES, help="report language for this render (default: config.yaml, else en)")
    rp.add_argument("--basemap", choices=config.BASEMAPS, help="none = bundled coastline (default); gibs = NASA GIBS true-colour underlay (fetches a public image)")
    rp.add_argument("--config", default=str(config.DEFAULT_PATH), help="config.yaml (default ./config.yaml)")
    rp.add_argument("--mode", choices=assess.MODES, default=assess.MODES[0], help="chlorophyll source rule")
    rp.set_defaults(func=cmd_report)
    su = sub.add_parser("setup", help="choose plants, write config.yaml, backfill their history, write the first report")
    su.add_argument("--plants", help="comma-separated plant ids (asked interactively when omitted)")
    su.add_argument("--out", help=f"report output folder (default {config.DEFAULT_OUT})")
    su.add_argument("--config", default=str(config.DEFAULT_PATH), help="where to write config.yaml")
    su.add_argument("--language", choices=i18n.LANGUAGES, help="report language (asked interactively when omitted; default en)")
    su.add_argument("--basemap", choices=config.BASEMAPS, default="none")
    su.add_argument("--yes", action="store_true", help="no prompts; overwrite an existing config.yaml")
    su.add_argument("--no-input", action="store_true", help="no prompts; refuse to overwrite an existing config.yaml")
    su.add_argument("--full-history", action="store_true",
                    help="backfill all history and rebuild the percentiles instead of loading the bundled export")
    su.add_argument("--skip-backfill", action="store_true", help="do not fetch history (percentiles must already exist)")
    su.add_argument("--delay", type=float, default=1.0, help="seconds to sleep between backfill requests")
    g = su.add_mutually_exclusive_group()
    g.add_argument("--schedule", action="store_true", help="also install the daily run (see `dbw schedule`)")
    g.add_argument("--no-schedule", action="store_true", help="do not offer the daily run")
    su.add_argument("--time", help="local HH:MM for the daily run (default: 07:00)")
    su.add_argument("--runner", help=f"{', '.join(schedule.RUNNERS)} (default: this platform's)")
    tgg = su.add_mutually_exclusive_group()
    tgg.add_argument("--telegram", action="store_true", help="also set up the Telegram channel (finds your chat id; see docs/telegram.md)")
    tgg.add_argument("--no-telegram", action="store_true", help="do not offer the Telegram channel")
    su.set_defaults(func=cmd_setup)
    sc = sub.add_parser("schedule", help="install, inspect or remove the daily run")
    sc.add_argument("action", choices=("install", "status", "remove"))
    sc.add_argument("--time", help="local HH:MM (default: config.yaml, else 07:00)")
    sc.add_argument("--runner", help=f"{', '.join(schedule.RUNNERS)} (default: config.yaml, else this platform's)")
    sc.add_argument("--dry-run", action="store_true", help="install: print what would be installed, change nothing")
    sc.add_argument("--config", default=str(config.DEFAULT_PATH), help="config.yaml (default ./config.yaml)")
    sc.set_defaults(func=cmd_schedule)
    tg = sub.add_parser("telegram", help="set up the Telegram channel: find the chat id of people who messaged the bot")
    tg.add_argument("action", choices=("chat-id",))
    tg.add_argument("--write", action="store_true", help="add the chat to config.yaml and turn telegram on")
    tg.add_argument("--pick", metavar="ID", help="with --write: which chat, when more than one has messaged the bot")
    tg.add_argument("--config", default=str(config.DEFAULT_PATH), help="config.yaml (default ./config.yaml)")
    tg.set_defaults(func=cmd_telegram)
    st = sub.add_parser("send-test", help="send a test message to every configured chat")
    st.add_argument("channel", choices=("telegram",))
    st.add_argument("--latest", action="store_true", help="also send the newest report's short message and HTML file")
    st.add_argument("--config", default=str(config.DEFAULT_PATH), help="config.yaml (default ./config.yaml)")
    st.set_defaults(func=cmd_send_test)
    pl = sub.add_parser("plants", help="list the plants, grouped by sea, north to south")
    pl.add_argument("--json", action="store_true", help="machine-readable output")
    pl.set_defaults(func=cmd_plants)
    sk = sub.add_parser("skill", help="install the Claude Code / Codex skill")
    sk.add_argument("action", choices=("install",))
    sk.add_argument("--claude", action="store_true", help="install for Claude Code (~/.claude/skills; the default)")
    sk.add_argument("--codex", action="store_true", help="install for Codex (~/.agents/skills)")
    sk.add_argument("--project", action="store_true", help="install under the current folder instead of your home folder")
    sk.add_argument("--force", action="store_true", help="replace an existing install")
    sk.set_defaults(func=cmd_skill)
    d = sub.add_parser("doctor", help="check registry, database and source reachability")
    d.set_defaults(func=cmd_doctor)
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy codepage; reports are Hebrew/Arabic
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (UpstreamUnreachable, FetchError) as e:
        print(f"NOAA data could not be fetched ({getattr(e, 'reason', None) or e}); try again later", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
