"""config.yaml: which plants to report on, where the report files go and in which language. Written by `dbw setup`
(or by hand from config.example.yaml). Secrets never live here. No network."""
import re
from pathlib import Path

import yaml

from dbw import i18n, schedule

DEFAULT_PATH = Path("config.yaml")
FORMATS = ("html", "md", "png", "txt")
BASEMAPS = ("none", "gibs")
DEFAULT_OUT = "./reports"

HEADER = """# Written by `dbw setup`. Edit by hand if you like; keys are documented in config.example.yaml.
# This file is gitignored: it is yours.
"""


class ConfigError(Exception):
    pass


def check(cfg):
    """Validate the shape of a loaded config; return it. Plant ids are checked against the registry by `write`."""
    plants = cfg.get("plants")
    if not isinstance(plants, list) or not plants:
        raise ConfigError("config: `plants` must be a non-empty list of plant ids")
    rep = cfg.get("report") or {}
    if not isinstance(rep, dict):
        raise ConfigError("config: `report` must be a mapping")
    if rep.get("basemap", "none") not in BASEMAPS:
        raise ConfigError(f"config: report.basemap must be one of {', '.join(BASEMAPS)}")
    bad = [f for f in rep.get("formats", FORMATS) if f not in FORMATS]
    if bad:
        raise ConfigError(f"config: report.formats has unknown format(s): {', '.join(bad)}")
    if rep.get("language", i18n.DEFAULT) not in i18n.LANGUAGES:
        raise ConfigError(f"config: report.language must be one of {', '.join(i18n.LANGUAGES)}")
    if "runner" in cfg and cfg["runner"] not in schedule.RUNNERS:
        raise ConfigError(f"config: runner must be one of {', '.join(schedule.RUNNERS)}")
    sched = cfg.get("schedule", {})
    if not isinstance(sched, dict):
        raise ConfigError("config: `schedule` must be a mapping (schedule: {time: \"HH:MM\"})")
    if "time" in sched:
        try:
            schedule.parse_time(sched["time"])
        except schedule.ScheduleError as e:
            raise ConfigError(f"config: schedule.time: {e}") from e
    _check_channels(cfg.get("channels"))
    return cfg


def _chat_id_ok(c):
    return isinstance(c, int) and not isinstance(c, bool) or isinstance(c, str) and bool(re.fullmatch(r"-?\d+", c.strip()))


def _check_channels(channels):
    """`channels.telegram`: {enabled: bool, chat_ids: [int or numeric string, ...]}. Channels not built yet are ignored."""
    if channels is None:
        return
    if not isinstance(channels, dict):
        raise ConfigError("config: `channels` must be a mapping (channels: {telegram: {enabled: true, chat_ids: [...]}})")
    tg = channels.get("telegram")
    if tg is None:
        return
    if not isinstance(tg, dict):
        raise ConfigError("config: channels.telegram must be a mapping ({enabled: true, chat_ids: [...]})")
    if not isinstance(tg.get("enabled", False), bool):
        raise ConfigError("config: channels.telegram.enabled must be true or false")
    ids = tg.get("chat_ids")
    if tg.get("enabled") and (not isinstance(ids, list) or not ids):
        raise ConfigError("config: channels.telegram.chat_ids must be a non-empty list while telegram is enabled "
                          "(run `dbw telegram chat-id --write`)")
    if ids is not None and (not isinstance(ids, list) or not all(_chat_id_ok(c) for c in ids)):
        bad = [c for c in ids if not _chat_id_ok(c)] if isinstance(ids, list) else ids
        raise ConfigError(f"config: channels.telegram.chat_ids must be a list of chat ids (whole numbers), not {bad}")


def telegram_chat_ids(cfg):
    """The chat ids to send to, as strings; empty when telegram is not enabled (or there is no config)."""
    tg = ((cfg or {}).get("channels") or {}).get("telegram") or {}
    return [str(c).strip() for c in tg.get("chat_ids") or []] if tg.get("enabled") else []


def add_telegram_chat(path, chat_id):
    """Enable telegram and add `chat_id` to its list (once); every other key is kept."""
    path = Path(path)
    cfg = check(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    tg = cfg.setdefault("channels", {}).setdefault("telegram", {})
    ids = list(tg.get("chat_ids") or [])
    new = int(str(chat_id).strip())
    if new not in [int(str(c).strip()) for c in ids]:
        ids.append(new)
    cfg["channels"]["telegram"] = {**tg, "enabled": True, "chat_ids": ids}
    check(cfg)
    path.write_text(HEADER + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return cfg


def load(path=None):
    """The parsed config, or None when the file does not exist."""
    path = Path(path) if path else DEFAULT_PATH
    if not path.exists():
        return None
    return check(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def report_settings(cfg):
    """(out dir, formats, basemap) with defaults filled in."""
    rep = (cfg or {}).get("report") or {}
    return Path(rep.get("out", DEFAULT_OUT)).expanduser(), list(rep.get("formats", FORMATS)), rep.get("basemap", "none")


def report_language(cfg):
    """The report language from the config (en when the config has none, or there is no config)."""
    return ((cfg or {}).get("report") or {}).get("language", i18n.DEFAULT)


def write(path, plants, out, boxes, formats=None, basemap="none", language=i18n.DEFAULT):
    """Validate against the registry and write config.yaml. Returns the dict written."""
    known = [b.id for b in boxes if b.kind == "plant"]
    if not plants:
        raise ConfigError("choose at least one plant")
    bad = [p for p in plants if p not in known]
    if bad:
        raise ConfigError(f"not a plant id: {', '.join(bad)} (plants: {', '.join(known)})")
    cfg = check({"plants": list(plants),
                 "report": {"out": str(out), "formats": list(formats or FORMATS), "basemap": basemap,
                            "language": language}})
    path = Path(path)
    path.write_text(HEADER + yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return cfg


def set_schedule(path, runner, time_text):
    """Record the installed runner and daily time in config.yaml; every other key is kept."""
    path = Path(path)
    cfg = check(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    cfg["runner"] = runner
    cfg["schedule"] = {"time": schedule.normalize_time(time_text)}
    path.write_text(HEADER + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return cfg


def prompt_plants(boxes, input_fn=input, say=print):
    """Ask which plants, by number or id (comma separated), until the answer is valid."""
    plants = [b for b in boxes if b.kind == "plant"]
    ids = [b.id for b in plants]
    for i, b in enumerate(plants, 1):
        say(f"  {i:2d}. {b.id:<16} {b.name or ''}")
    while True:
        picked, bad = [], []
        for tok in (t.strip() for t in input_fn("Plants (numbers or ids, comma separated): ").split(",")):
            if not tok:
                continue
            pid = ids[int(tok) - 1] if tok.isdigit() and 0 < int(tok) <= len(ids) else tok
            (picked if pid in ids else bad).append(pid)
        if picked and not bad:
            return list(dict.fromkeys(picked))
        say(f"  not understood: {', '.join(bad) or 'nothing chosen'}")


def prompt_language(input_fn=input, say=print):
    """Ask the report language by code (Enter = English) until the answer is valid."""
    menu = ", ".join(f"{code} {i18n.load(code)['meta']['name']}" for code in i18n.LANGUAGES)
    while True:
        answer = input_fn(f"Report language ({menu}) [{i18n.DEFAULT}]: ").strip().lower()
        if not answer:
            return i18n.DEFAULT
        if answer in i18n.LANGUAGES:
            return answer
        say(f"  not understood: {answer}")
