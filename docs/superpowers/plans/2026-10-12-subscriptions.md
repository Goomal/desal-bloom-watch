# Subscriptions (Telegram sign-up bot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** People sign up to the daily report through a Telegram bot (`/start`), each choosing plants and language; the admin adds and removes people (`/add`, `/remove`, `/list`, or `dbw subscribers ...`); the existing daily `dbw run` sends every subscriber their report.

**Architecture:** Four new modules. `dbw/subscribers.py` owns the new SQLite tables (subscribers, contacts, conversations, bot_state). `dbw/bot.py` is the conversation state machine plus the long-poll loop behind `dbw bot run`. `dbw/bot_service.py` installs that loop to start at login (launchd / cron `@reboot` / Task Scheduler), shaped like `dbw/schedule.py`. `dbw/deliver.py` builds one report per (plants, language) group and sends it, called from `dbw run`. Telegram calls stay in `dbw/channels/telegram.py`, which gains buttons, callback answers and an update offset.

**Tech Stack:** Python ≥3.11 standard library (urllib, sqlite3, json, plistlib), PyYAML, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-12-subscriptions-design.md`

## Global Constraints

- `requires-python = ">=3.11"`; dependencies stay `PyYAML>=6`, `matplotlib>=3.8`. Telegram uses "only the standard library".
- Channel now: **Telegram only**. Email dropped; WhatsApp is phase 2 (leave the `channel` column and the `senders` map, nothing else).
- Languages: `en` / `he` / `ar` (`dbw.i18n.LANGUAGES`). Every new locale key exists in all three files with the same `{placeholders}`, Western digits only (`tests/test_i18n.py` enforces this).
- Storage: new tables in the existing SQLite database `data/dbw.sqlite` (path from `store.default_path()`, overridable by `DBW_DB`).
- The bot never sends the daily report; `dbw run` does. The admin's own report (`channels.telegram.chat_ids`) is unchanged.
- The bot token never appears in a log or an error line: everything goes through `telegram.redact`.
- Messages are plain text, no `parse_mode`.
- Tests are offline and pass on Linux, macOS and Windows (CI: ubuntu/macos/windows × Python 3.11/3.13, `PYTHONUTF8=1`). All Telegram traffic goes through the `telegram._http` fake (`tests/test_telegram.py::Http`); all service-manager calls go through a `run` fake (`tests/test_schedule.py::FakeRun`).
- Public repo: no real chat ids, names, emails or tokens in code, tests or docs. Fake token = `tests/test_telegram.py::TOKEN`. Never push the branch `archive/private-history`.
- Work on branch `subscriptions-design` (holds the spec and this plan); open one PR to `main` at the end so the Windows CI matrix runs.
- Run commands from the repo root with the venv: `.venv/bin/python -m pytest ...` (Windows: `.venv\Scripts\python -m pytest ...`).

## Decisions this plan adds to the spec (flag in the PR description)

1. `subscribers.last_sent` (date of the last report sent): a second `dbw run` the same day does not send again.
2. `bot_state` table: holds the Telegram update offset, so a bot restart does not replay old updates.
3. `contacts.type` (private / group / supergroup) and `contacts.last` (epoch seconds of the last message): needed to offer only private chats as admins and to show chats newest first.
4. Self sign-up works in private chats only. A group is added by the admin typing `/add` in that group ("This chat").
5. `/stop` (or the word "stop") is everyone's stop command, and the help text and the "Subscribed" message say so. `/remove` from a non-admin means the same; from the admin it opens the removal list, so the admin stops their own report with `/stop`.
6. A 403 removal is not counted as a failure (the run stays `ok`); the admin is told.
7. `dbw doctor` checks the bot and `admin_ids` only once subscriptions are in use (admin_ids set, or any subscriber), so existing users see no new FAIL.
8. Linux uses a cron `@reboot` line (following `dbw/schedule.py`), not systemd. Windows starts the bot with `pythonw.exe -m dbw.cli` so no console window stays open.
9. A change to `admin_ids` takes effect when the bot restarts.
10. `dbw subscribers add/remove` (on the computer) do not message the person; the Telegram `/add` and `/remove` do.
11. `dbw run --date ...` never sends to subscribers (only the daily run without a date does).
12. `/add` lists the 30 chats that messaged the bot most recently; older ones can be added with `dbw subscribers add`.
13. Subscriber reports use the admin's `report.basemap`; with `gibs`, each (plants, language) group fetches its own NASA underlay.
14. When the admin adds someone who has an unfinished sign-up, that questionnaire is closed.
15. The installed bot job passes `--config <absolute path>` like the daily job, so it finds the config and the `.env` next to it.

## Invariant traces

Each spec invariant (spec, "Invariants") and the test that holds it:

- I1 Test: `tests/test_subscribers.py::test_one_active_subscription_per_address` (Task 2)
- I2 Test: `tests/test_deliver.py::test_a_second_run_the_same_day_sends_nothing_new` and `::test_a_dated_run_never_sends_to_subscribers` (Task 9)
- I3 Test: `tests/test_deliver.py::test_one_failure_does_not_stop_the_others_and_makes_the_run_partial` (Task 9)
- I4 Test: `tests/test_deliver.py::test_a_403_removes_the_subscriber_and_tells_the_admin` (Task 9)
- I5 Test: `tests/test_bot_admin.py::test_admin_commands_are_refused_to_others`, `::test_only_the_admin_can_press_remove`, `::test_a_group_member_cannot_use_the_admins_buttons` (Task 6)
- I6 Test: `tests/test_bot_runtime.py::test_only_one_bot_at_a_time` and `::test_bot_run_refuses_a_second_copy` (Task 7)
- I7 Test: `tests/test_bot_runtime.py::test_the_log_is_stamped_and_never_holds_the_token` (Task 7), and the existing redaction tests in `tests/test_telegram.py`
- I8 Test: `tests/test_deliver.py::test_one_report_per_group_and_each_person_gets_it` (the admin's `reports/` file is still written) and the existing run tests in `tests/test_telegram_cli.py` (Task 9 runs them)

## Review Focus

1. **The daily run and the bot write the database at the same time** → the bot logs "database busy", keeps the update and retries it; the daily run finishes. Test: Task 7 `test_a_busy_database_keeps_the_update_for_the_next_poll`.
2. **A plant id disappears from `plants.yaml` while a subscriber still has it** → `dbw run` does not crash; that subscriber gets the plants that still exist. Tests: Task 9 `test_a_plant_gone_from_the_registry_is_skipped_not_fatal`.
3. **`dbw run` twice the same day, or `dbw run --date`** → subscribers get exactly one report per day and none from a dated re-run. Tests: Task 9 `test_a_second_run_the_same_day_sends_nothing_new`, `test_a_dated_run_never_sends_to_subscribers`.
4. **The bot restarts mid-conversation or mid-batch** → nobody loses their place and nobody is subscribed twice. Tests: Task 5 `test_the_questionnaire_survives_a_restart`, Task 2 `test_one_active_subscription_per_address`, Task 7 `test_the_offset_is_saved_so_a_restart_does_not_replay`.
5. **Old or foreign buttons are tapped** (yesterday's keyboard, a [Remove] for someone who already left, a group member tapping the admin's buttons) → a short "expired" / "admin only" toast and no change. Tests: Task 5 `test_an_old_button_is_expired_and_changes_nothing`, Task 6 `test_a_stale_remove_button_is_expired`, `test_a_group_member_cannot_use_the_admins_buttons`.

---

## File map

| File | Status | Responsibility |
|---|---|---|
| `dbw/config.py` | modify | `channels.telegram.admin_ids` validation, `telegram_admin_ids`, `add_telegram_admin` |
| `dbw/subscribers.py` | create | tables + CRUD for subscribers, contacts, conversations, bot_state |
| `dbw/store.py` | modify | `connect` also creates the subscriber tables |
| `dbw/channels/telegram.py` | modify | `TelegramError.code`, `chat_name`, `get_updates(offset, timeout)`, `send_buttons`, `edit_buttons`, `answer_callback` |
| `dbw/locales/{en,he,ar}.json` | modify | `bot.*` strings |
| `dbw/bot.py` | create | `Bot` (conversations, admin commands), poll loop, lock, log |
| `dbw/bot_service.py` | create | install / uninstall / status of the always-on bot |
| `dbw/deliver.py` | create | subscriber reports per group, send, 403 removal |
| `dbw/schedule.py` | modify | `telegram_failed_for(n, m)` |
| `dbw/cli.py` | modify | `dbw bot`, `dbw subscribers`, `dbw telegram admin-id`, run integration, doctor |
| `tests/conftest.py` | modify | every test gets its own database |
| `tests/test_subscribers.py`, `tests/test_bot.py`, `tests/test_bot_admin.py`, `tests/test_bot_runtime.py`, `tests/test_bot_service.py`, `tests/test_deliver.py`, `tests/test_subscribers_cli.py` | create | tests |
| `docs/telegram.md`, `config.example.yaml`, `README.md` | modify | docs |

---

### Task 1: `admin_ids` in config.yaml

**Files:**
- Modify: `dbw/config.py` (`_check_channels`, new `telegram_admin_ids`, `add_telegram_admin`)
- Test: `tests/test_subscribers_cli.py` (create; later tasks add to it)

**Interfaces:**
- Produces: `config.telegram_admin_ids(cfg) -> list[int]` (empty when unset or no config; independent of `enabled`); `config.add_telegram_admin(path, user_id) -> dict` (adds once, keeps every other key, does not turn telegram on).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_subscribers_cli.py`:

```python
"""Subscriptions on the computer: admin_ids in config.yaml, `dbw subscribers ...`, `dbw telegram admin-id`.
Offline; the fake token is built at run time."""
import pytest
import yaml

from dbw import config, registry


def check(tg):
    return config.check({"plants": ["hadera"], "channels": {"telegram": tg}})


def test_admin_ids_load_as_ints_whatever_their_yaml_type():
    assert config.telegram_admin_ids(check({"admin_ids": [111, "222"]})) == [111, 222]


def test_no_admin_ids_is_an_empty_list():
    assert config.telegram_admin_ids(None) == []
    assert config.telegram_admin_ids({"plants": ["hadera"]}) == []
    assert config.telegram_admin_ids(check({"enabled": False})) == []


def test_admin_ids_alone_do_not_turn_on_the_admin_report():
    assert config.telegram_chat_ids(check({"admin_ids": [111]})) == []


@pytest.mark.parametrize("bad", [111, ["abc"], [True], [1.5], "111"])
def test_bad_admin_ids_are_a_one_line_config_error(bad):
    with pytest.raises(config.ConfigError, match="admin_ids"):
        check({"admin_ids": bad})


def test_add_telegram_admin_adds_once_and_keeps_every_other_key(tmp_path):
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md"], language="he")
    config.add_telegram_admin(p, "111")
    config.add_telegram_admin(p, 111)
    cfg = config.load(p)
    assert cfg["channels"]["telegram"]["admin_ids"] == [111]
    assert cfg["plants"] == ["ashkelon"] and cfg["report"]["language"] == "he"
    assert cfg["channels"]["telegram"].get("enabled") is not True
    assert yaml.safe_load(p.read_text(encoding="utf-8"))["channels"]["telegram"]["admin_ids"] == [111]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_subscribers_cli.py -v`
Expected: FAIL with `AttributeError: module 'dbw.config' has no attribute 'telegram_admin_ids'`.

- [ ] **Step 3: Implement**

In `dbw/config.py`, at the end of `_check_channels` (after the `chat_ids` checks) add:

```python
    admins = tg.get("admin_ids")
    if admins is not None and (not isinstance(admins, list) or not all(_chat_id_ok(c) for c in admins)):
        raise ConfigError(f"config: channels.telegram.admin_ids must be a list of Telegram user ids (whole numbers), "
                          f"not {admins} (run `dbw telegram admin-id --write`)")
```

Update the `_check_channels` docstring to: `"""`channels.telegram`: {enabled: bool, chat_ids: [...], admin_ids: [...]}, ids are ints or numeric strings. Channels not built yet are ignored."""`

After `telegram_chat_ids` add:

```python
def telegram_admin_ids(cfg):
    """The admins' Telegram user ids (a private chat's id is its user's id), as ints; empty when none are set.
    Independent of `enabled`: the admin may run the sign-up bot without receiving the admin report."""
    tg = ((cfg or {}).get("channels") or {}).get("telegram") or {}
    return [int(str(c).strip()) for c in tg.get("admin_ids") or []]


def add_telegram_admin(path, user_id):
    """Add `user_id` to channels.telegram.admin_ids (once); every other key is kept and telegram is not turned on."""
    path = Path(path)
    cfg = check(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    tg = cfg.setdefault("channels", {}).setdefault("telegram", {})
    ids = [int(str(c).strip()) for c in tg.get("admin_ids") or []]
    new = int(str(user_id).strip())
    if new not in ids:
        ids.append(new)
    cfg["channels"]["telegram"] = {**tg, "admin_ids": ids}
    check(cfg)
    path.write_text(HEADER + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return cfg
```

Note `"111"` (a bare string, not a list) must fail: the `isinstance(admins, list)` test does that.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_subscribers_cli.py tests/test_telegram_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dbw/config.py tests/test_subscribers_cli.py
git commit -m "config: channels.telegram.admin_ids"
```

---

### Task 2: Subscriber tables (`dbw/subscribers.py`)

**Files:**
- Create: `dbw/subscribers.py`
- Modify: `dbw/store.py:47-55` (`connect`)
- Modify: `tests/conftest.py` (every test gets its own database)
- Test: `tests/test_subscribers.py`

**Interfaces:**
- Produces (all take an open `sqlite3.Connection` from `store.connect`; addresses are strings):
  - `CHANNELS = ("telegram",)`, `ACTIVE = "active"`, `REMOVED = "removed"`, `NAME_MAX = 64`, `SCHEMA` (tuple of SQL)
  - `@dataclass(frozen=True) Subscriber(id: int, name: str, channel: str, address: str, plants: tuple[str, ...], language: str, status: str, added_by: str, created_at: str, removed_at: str | None, last_sent: str | None)`
  - `add(conn, name, channel, address, plants, language, added_by) -> Subscriber` — raises `ValueError` ("already subscribed" when that address is active; bad name/plants/language/channel/added_by)
  - `get(conn, sub_id) -> Subscriber | None`; `get_active(conn, channel, address) -> Subscriber | None`; `active(conn) -> list[Subscriber]` (by id)
  - `update(conn, sub_id, plants=None, language=None) -> Subscriber`
  - `remove(conn, sub_id) -> Subscriber | None` (the removed row; None when it was not active)
  - `mark_sent(conn, sub_id, day: date)`; `wanted_plants(conn) -> list[str]` (sorted union of active plants)
  - `touch_contact(conn, channel, address, name, type, last: int)`; `contacts(conn, channel="telegram") -> list[dict]` with keys `address, name, type, last`, newest first
  - `get_conversation(conn, channel, address) -> tuple[str, dict] | None`; `set_conversation(conn, channel, address, step, data: dict)`; `clear_conversation(conn, channel, address)`
  - `get_state(conn, key, default=None) -> str | None`; `set_state(conn, key, value: str)`
  - `export(conn) -> list[dict]` (every row, removed ones too, JSON-ready)

- [ ] **Step 1: Give every test its own database**

Today a test that forgets `DBW_DB` opens the real `data/dbw.sqlite`. Once the CLI reads contacts from it, the developer's real contacts would leak into test output. In `tests/conftest.py` add (and extend the module docstring with "and its own empty database"):

```python
@pytest.fixture(autouse=True)
def no_real_database_by_accident(tmp_path, monkeypatch):
    """A test that sets DBW_DB itself overrides this; nothing ever opens the real data/dbw.sqlite."""
    monkeypatch.setenv("DBW_DB", str(tmp_path / "auto.sqlite"))
```

Run: `.venv/bin/python -m pytest -q`
Expected: same result as before the change (on Windows without symlinks: the one known `test_codex_link...` failure).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_subscribers.py`:

```python
"""dbw/subscribers.py: the subscriber, contact, conversation and bot_state tables. Offline."""
from datetime import date

import pytest

from dbw import store, subscribers as subs


@pytest.fixture
def conn(tmp_path):
    return store.connect(tmp_path / "t.sqlite")


def dana(conn, address="111", plants=("hadera", "ashkelon"), lang="he", by="self"):
    return subs.add(conn, "Dana", "telegram", address, plants, lang, by)


def test_store_connect_creates_the_subscriber_tables(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"subscribers", "contacts", "conversations", "bot_state"} <= names


def test_add_then_read_back(conn):
    s = dana(conn)
    assert (s.name, s.channel, s.address, s.plants, s.language, s.status, s.added_by) == \
        ("Dana", "telegram", "111", ("hadera", "ashkelon"), "he", "active", "self")
    assert subs.get(conn, s.id) == s == subs.get_active(conn, "telegram", "111")
    assert subs.active(conn) == [s] and s.created_at and s.removed_at is None and s.last_sent is None


def test_one_active_subscription_per_address(conn):
    dana(conn)
    with pytest.raises(ValueError, match="already subscribed"):
        dana(conn, plants=("eilat",))
    assert len(subs.active(conn)) == 1


def test_remove_then_subscribe_again(conn):
    s = dana(conn)
    gone = subs.remove(conn, s.id)
    assert gone.status == "removed" and gone.removed_at
    assert subs.remove(conn, s.id) is None  # already removed
    assert subs.active(conn) == [] and subs.get_active(conn, "telegram", "111") is None
    again = dana(conn, plants=("eilat",))
    assert again.id != s.id and subs.active(conn) == [again]


def test_update_plants_and_language(conn):
    s = dana(conn)
    assert subs.update(conn, s.id, plants=["eilat"]).plants == ("eilat",)
    assert subs.update(conn, s.id, language="ar").language == "ar"


def test_wanted_plants_is_the_union_of_active_subscribers(conn):
    dana(conn, "1", ("hadera", "ashkelon"))
    dana(conn, "2", ("eilat", "hadera"))
    subs.remove(conn, dana(conn, "3", ("sorek_a",)).id)
    assert subs.wanted_plants(conn) == ["ashkelon", "eilat", "hadera"]


def test_mark_sent_records_the_day(conn):
    s = dana(conn)
    subs.mark_sent(conn, s.id, date(2026, 10, 12))
    assert subs.get(conn, s.id).last_sent == "2026-10-12"


@pytest.mark.parametrize("kw, why", [
    ({"name": "  "}, "name"),
    ({"name": "x" * 65}, "name"),
    ({"plants": ()}, "plant"),
    ({"language": "fr"}, "language"),
    ({"channel": "email"}, "channel"),
    ({"added_by": "robot"}, "added_by"),
])
def test_bad_values_are_refused(conn, kw, why):
    args = {"name": "Dana", "channel": "telegram", "address": "111", "plants": ("hadera",), "language": "en",
            "added_by": "self", **kw}
    with pytest.raises(ValueError, match=why):
        subs.add(conn, **args)


def test_contacts_are_upserted_and_listed_newest_first(conn):
    subs.touch_contact(conn, "telegram", "111", "Dana", "private", 100)
    subs.touch_contact(conn, "telegram", "-100222", "Plant ops", "supergroup", 200)
    subs.touch_contact(conn, "telegram", "111", "Dana L", "private", 300)
    assert subs.contacts(conn) == [
        {"address": "111", "name": "Dana L", "type": "private", "last": 300},
        {"address": "-100222", "name": "Plant ops", "type": "supergroup", "last": 200},
    ]


def test_a_conversation_survives_a_new_connection(tmp_path):
    path = tmp_path / "t.sqlite"
    subs.set_conversation(store.connect(path), "telegram", "111", "plants", {"flow": "self", "picked": ["hadera"]})
    conn = store.connect(path)
    assert subs.get_conversation(conn, "telegram", "111") == ("plants", {"flow": "self", "picked": ["hadera"]})
    subs.clear_conversation(conn, "telegram", "111")
    assert subs.get_conversation(conn, "telegram", "111") is None


def test_bot_state_round_trip(conn):
    assert subs.get_state(conn, "telegram_offset") is None
    subs.set_state(conn, "telegram_offset", "42")
    subs.set_state(conn, "telegram_offset", "43")
    assert subs.get_state(conn, "telegram_offset") == "43"


def test_export_has_every_row_including_removed(conn):
    subs.remove(conn, dana(conn, "1").id)
    dana(conn, "2")
    rows = subs.export(conn)
    assert [(r["address"], r["status"]) for r in rows] == [("1", "removed"), ("2", "active")]
    assert rows[0]["plants"] == ["hadera", "ashkelon"]
```

- [ ] **Step 3: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_subscribers.py -v`
Expected: FAIL with `ImportError: cannot import name 'subscribers' from 'dbw'`.

- [ ] **Step 4: Implement `dbw/subscribers.py`**

```python
"""Subscribers to the daily report, the chats that have messaged the bot, where each chat is in a bot questionnaire,
and the bot's own small state (the Telegram update offset). Tables in the main SQLite database; dbw/store.py creates
them. No network."""
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from dbw import i18n

CHANNELS = ("telegram",)  # "whatsapp" is phase 2
ACTIVE, REMOVED = "active", "removed"
ADDED_BY = ("self", "admin")
NAME_MAX = 64

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS subscribers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, channel TEXT NOT NULL, address TEXT NOT NULL,
        plants TEXT NOT NULL, language TEXT NOT NULL, status TEXT NOT NULL, added_by TEXT NOT NULL,
        created_at TEXT NOT NULL, removed_at TEXT, last_sent TEXT)""",
    # one active subscription per chat; removed rows stay as history
    """CREATE UNIQUE INDEX IF NOT EXISTS subscribers_one_active ON subscribers(channel, address)
        WHERE status = 'active'""",
    """CREATE TABLE IF NOT EXISTS contacts (
        channel TEXT NOT NULL, address TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
        last INTEGER NOT NULL, PRIMARY KEY (channel, address))""",
    """CREATE TABLE IF NOT EXISTS conversations (
        channel TEXT NOT NULL, address TEXT NOT NULL, step TEXT NOT NULL, data TEXT NOT NULL,
        updated_at TEXT NOT NULL, PRIMARY KEY (channel, address))""",
    "CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
)

_COLS = "id, name, channel, address, plants, language, status, added_by, created_at, removed_at, last_sent"


@dataclass(frozen=True)
class Subscriber:
    id: int
    name: str
    channel: str
    address: str
    plants: tuple
    language: str
    status: str
    added_by: str
    created_at: str
    removed_at: str | None
    last_sent: str | None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sub(row):
    return None if row is None else Subscriber(*row[:4], tuple(json.loads(row[4])), *row[5:])


def _one(conn, where, params):
    return _sub(conn.execute(f"SELECT {_COLS} FROM subscribers WHERE {where}", params).fetchone())


def clean_name(name):
    """`name` with runs of whitespace made one space; ValueError when empty or longer than NAME_MAX."""
    name = " ".join(str(name).split())
    if not name or len(name) > NAME_MAX:
        raise ValueError(f"name must be 1 to {NAME_MAX} characters")
    return name


def _check(plants, language):
    if not plants:
        raise ValueError("choose at least one plant")
    if language not in i18n.LANGUAGES:
        raise ValueError(f"language must be one of {', '.join(i18n.LANGUAGES)}")


def add(conn, name, channel, address, plants, language, added_by):
    """Subscribe one chat. Plant ids are checked against the registry by the callers (the bot shows only registry
    plants; the CLI uses config.prompt_plants)."""
    name = clean_name(name)
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of {', '.join(CHANNELS)}")
    if added_by not in ADDED_BY:
        raise ValueError(f"added_by must be one of {', '.join(ADDED_BY)}")
    _check(plants, language)
    address = str(address)
    if get_active(conn, channel, address):
        raise ValueError(f"{channel} {address} is already subscribed")
    with conn:
        cur = conn.execute("INSERT INTO subscribers(name, channel, address, plants, language, status, added_by, created_at)"
                           " VALUES (?,?,?,?,?,?,?,?)",
                           (name, channel, address, json.dumps(list(plants)), language, ACTIVE, added_by, _now()))
    return get(conn, cur.lastrowid)


def get(conn, sub_id):
    return _one(conn, "id=?", (sub_id,))


def get_active(conn, channel, address):
    return _one(conn, "channel=? AND address=? AND status=?", (channel, str(address), ACTIVE))


def active(conn):
    return [_sub(r) for r in conn.execute(f"SELECT {_COLS} FROM subscribers WHERE status=? ORDER BY id", (ACTIVE,))]


def update(conn, sub_id, plants=None, language=None):
    s = get(conn, sub_id)
    plants = list(plants) if plants is not None else list(s.plants)
    language = language or s.language
    _check(plants, language)
    with conn:
        conn.execute("UPDATE subscribers SET plants=?, language=? WHERE id=?", (json.dumps(plants), language, sub_id))
    return get(conn, sub_id)


def remove(conn, sub_id):
    """Mark an active subscriber removed. -> the removed row, or None when it was not active."""
    with conn:
        n = conn.execute("UPDATE subscribers SET status=?, removed_at=? WHERE id=? AND status=?",
                         (REMOVED, _now(), sub_id, ACTIVE)).rowcount
    return get(conn, sub_id) if n else None


def mark_sent(conn, sub_id, day):
    with conn:
        conn.execute("UPDATE subscribers SET last_sent=? WHERE id=?", (day.isoformat(), sub_id))


def wanted_plants(conn):
    return sorted({p for s in active(conn) for p in s.plants})


def touch_contact(conn, channel, address, name, type, last):
    with conn:
        conn.execute("INSERT INTO contacts(channel, address, name, type, last) VALUES (?,?,?,?,?)"
                     " ON CONFLICT(channel, address) DO UPDATE SET name=excluded.name, type=excluded.type,"
                     " last=MAX(last, excluded.last)", (channel, str(address), name, type, int(last or 0)))


def contacts(conn, channel="telegram"):
    q = "SELECT address, name, type, last FROM contacts WHERE channel=? ORDER BY last DESC"
    return [{"address": a, "name": n, "type": t, "last": l} for a, n, t, l in conn.execute(q, (channel,))]


def get_conversation(conn, channel, address):
    row = conn.execute("SELECT step, data FROM conversations WHERE channel=? AND address=?",
                       (channel, str(address))).fetchone()
    return None if row is None else (row[0], json.loads(row[1]))


def set_conversation(conn, channel, address, step, data):
    with conn:
        conn.execute("INSERT OR REPLACE INTO conversations(channel, address, step, data, updated_at) VALUES (?,?,?,?,?)",
                     (channel, str(address), step, json.dumps(data, ensure_ascii=False), _now()))


def clear_conversation(conn, channel, address):
    with conn:
        conn.execute("DELETE FROM conversations WHERE channel=? AND address=?", (channel, str(address)))


def get_state(conn, key, default=None):
    row = conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_state(conn, key, value):
    with conn:
        conn.execute("INSERT OR REPLACE INTO bot_state(key, value) VALUES (?,?)", (key, str(value)))


def export(conn):
    rows = conn.execute(f"SELECT {_COLS} FROM subscribers ORDER BY id")
    return [{**asdict(s), "plants": list(s.plants)} for s in map(_sub, rows)]
```

In `dbw/store.py` add `from dbw import subscribers` to the imports and change the loop in `connect` to:

```python
    for stmt in SCHEMA_EXTRA + subscribers.SCHEMA:
        conn.execute(stmt)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_subscribers.py tests/test_store.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dbw/subscribers.py dbw/store.py tests/test_subscribers.py tests/conftest.py
git commit -m "subscribers: tables for subscribers, contacts, conversations, bot state"
```

---

### Task 3: Telegram buttons, callbacks and update offset

**Files:**
- Modify: `dbw/channels/telegram.py`
- Test: `tests/test_telegram.py` (append)

**Interfaces:**
- Produces:
  - `TelegramError(message, code=None)` with `.code` = the HTTP status when Telegram answered (403 = blocked bot / deleted account)
  - `LONG_POLL = 25`; `get_updates(token, offset=None, timeout=0) -> list` (old call `get_updates(token)` posts `{"timeout": 0}` exactly as before)
  - `chat_name(chat: dict) -> str` (the naming rule `chats_from_updates` uses today)
  - `send_buttons(token, chat_id, text, rows) -> dict` (the sent message); `rows = [[(label, callback_data), ...], ...]`
  - `edit_buttons(token, chat_id, message_id, text, rows)` (Telegram's "message is not modified" is ignored)
  - `answer_callback(token, callback_id, text="")`
  - `CALLBACK_LIMIT = 64`: callback data longer than 64 bytes raises `ValueError` before any request

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram.py`:

```python
# --- buttons, callbacks, offset -------------------------------------------------------------------------------

def test_a_telegram_error_carries_the_http_status(http):
    http.script = [fail(403, "Forbidden: bot was blocked by the user")]
    with pytest.raises(telegram.TelegramError) as e:
        telegram.send_message(TOKEN, "42", "hi")
    assert e.value.code == 403


def test_get_updates_keeps_its_old_body_and_can_long_poll_from_an_offset(http):
    telegram.get_updates(TOKEN)
    telegram.get_updates(TOKEN, offset=7, timeout=telegram.LONG_POLL)
    assert [json.loads(c.body) for c in http.calls] == [{"timeout": 0}, {"timeout": 25, "offset": 7}]
    assert telegram.LONG_POLL < telegram.TIMEOUT  # the HTTP read must outlast the long poll


def test_send_buttons_posts_an_inline_keyboard(http):
    http.script = [(200, {"ok": True, "result": {"message_id": 9}})]
    sent = telegram.send_buttons(TOKEN, 42, "Pick", [[("Hadera", "p:hadera")], [("Done", "p:done")]])
    assert sent == {"message_id": 9}
    assert json.loads(http.calls[0].body) == {"chat_id": "42", "text": "Pick", "reply_markup": {"inline_keyboard": [
        [{"text": "Hadera", "callback_data": "p:hadera"}], [{"text": "Done", "callback_data": "p:done"}]]}}


def test_callback_data_over_64_bytes_is_refused_before_sending(http):
    with pytest.raises(ValueError, match="64"):
        telegram.send_buttons(TOKEN, 42, "Pick", [[("x", "p:" + "a" * 63)]])
    assert http.calls == []


def test_edit_buttons_ignores_message_is_not_modified_only(http):
    http.script = [fail(400, "Bad Request: message is not modified"), fail(400, "Bad Request: message to edit not found")]
    telegram.edit_buttons(TOKEN, 42, 9, "Pick", [])
    with pytest.raises(telegram.TelegramError, match="not found"):
        telegram.edit_buttons(TOKEN, 42, 9, "Pick", [])
    assert http.calls[0].method == "editMessageText"
    assert json.loads(http.calls[0].body) == {"chat_id": "42", "message_id": 9, "text": "Pick",
                                              "reply_markup": {"inline_keyboard": []}}


def test_answer_callback_with_and_without_a_toast(http):
    telegram.answer_callback(TOKEN, "cb1")
    telegram.answer_callback(TOKEN, "cb2", "Tick at least one plant.")
    assert [json.loads(c.body) for c in http.calls] == [
        {"callback_query_id": "cb1"}, {"callback_query_id": "cb2", "text": "Tick at least one plant."}]


def test_chat_name_is_the_rule_chats_from_updates_uses():
    assert telegram.chat_name({"title": "Plant ops", "first_name": "x"}) == "Plant ops"
    assert telegram.chat_name({"first_name": "A", "last_name": "B"}) == "A B"
    assert telegram.chat_name({"username": "ab"}) == "@ab"
    assert telegram.chat_name({}) == ""
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_telegram.py -v`
Expected: the new tests FAIL (`AttributeError: 'TelegramError' object has no attribute 'code'`, `no attribute 'send_buttons'`, ...).

- [ ] **Step 3: Implement**

In `dbw/channels/telegram.py`:

1. Constants: after `TIMEOUT = 30` add
```python
LONG_POLL = 25  # getUpdates long-poll seconds: shorter than TIMEOUT, so the HTTP read never times out first
CALLBACK_LIMIT = 64  # bytes of callback_data Telegram accepts on a button
```

2. Replace the `TelegramError` class:
```python
class TelegramError(Exception):
    """One plain line the user can act on. Never contains the token. `code`: the HTTP status when Telegram answered
    (403 = the person blocked the bot or deleted their account), else None."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code
```

3. In `_call`, change the last line to pass the status:
```python
        raise TelegramError(redact(f"{method}: HTTP {code}" + (f": {description}" if description else ""), token), code)
```

4. After `send_report` add:
```python
def _keyboard(rows):
    for row in rows:
        for _, data in row:
            if len(data.encode("utf-8")) > CALLBACK_LIMIT:
                raise ValueError(f"button data over {CALLBACK_LIMIT} bytes: {data!r}")
    return {"inline_keyboard": [[{"text": label, "callback_data": data} for label, data in row] for row in rows]}


def send_buttons(token, chat_id, text, rows):
    """One message with inline buttons; rows = [[(label, callback data), ...], ...]. -> the sent message."""
    body = {"chat_id": str(chat_id), "text": text, "reply_markup": _keyboard(rows)}
    return _call(token, "sendMessage", json.dumps(body).encode("utf-8"))


def edit_buttons(token, chat_id, message_id, text, rows):
    """Replace a sent message's text and buttons (rows=[] removes them). Re-sending the same content is not an error."""
    body = {"chat_id": str(chat_id), "message_id": message_id, "text": text, "reply_markup": _keyboard(rows)}
    try:
        _call(token, "editMessageText", json.dumps(body).encode("utf-8"))
    except TelegramError as e:
        if "message is not modified" not in str(e):
            raise


def answer_callback(token, callback_id, text=""):
    """Stop the button's spinner; `text` shows as a short toast."""
    body = {"callback_query_id": callback_id, **({"text": text} if text else {})}
    _call(token, "answerCallbackQuery", json.dumps(body).encode("utf-8"))
```

5. Replace `get_updates`:
```python
def get_updates(token, offset=None, timeout=0):
    """The pending updates for the bot (what people sent it since it last fetched them; Telegram keeps them 24 h).
    `offset` confirms every update below it; `timeout` > 0 long-polls. `allowed_updates` is never sent: Telegram
    remembers it, and `dbw telegram chat-id` needs every update kind."""
    body = {"timeout": timeout, **({"offset": offset} if offset is not None else {})}
    return _call(token, "getUpdates", json.dumps(body).encode("utf-8")) or []
```

6. Add `chat_name` above `chats_from_updates` and use it there:
```python
def chat_name(chat):
    """A group's title, else a person's first and last name, else @username, else ''."""
    return (chat.get("title") or " ".join(p for p in (chat.get("first_name"), chat.get("last_name")) if p)
            or (f"@{chat['username']}" if chat.get("username") else ""))
```
and in `chats_from_updates` replace the `name = (...)` expression with `name = chat_name(chat)`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_telegram.py tests/test_telegram_cli.py -v`
Expected: PASS (the old `getUpdates` and chat-name tests still pass).

- [ ] **Step 5: Commit**

```bash
git add dbw/channels/telegram.py tests/test_telegram.py
git commit -m "telegram: buttons, callback answers, update offset, error status"
```

---

### Task 4: Bot wording in en / he / ar

**Files:**
- Modify: `dbw/locales/en.json`, `dbw/locales/he.json`, `dbw/locales/ar.json` (the `strings` object)
- Test: `tests/test_i18n.py` (append)

**Interfaces:**
- Produces the keys below, rendered with `i18n.Msg(code, **params).render(lang)`. Placeholders: `{name}` (str), `{plants}` (list of display names; Msg joins it with the language's separator), `{language}` (a language's own name), `{max}` (int).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
BOT_KEYS = ("bot.ask_name", "bot.bad_name", "bot.ask_plants", "bot.done", "bot.need_plant", "bot.confirm", "bot.yes",
            "bot.no", "bot.subscribed", "bot.cancelled", "bot.menu", "bot.change_plants", "bot.change_lang", "bot.stop",
            "bot.saved", "bot.stop_confirm", "bot.stopped", "bot.not_subscribed", "bot.removed_by_admin", "bot.expired",
            "bot.help", "bot.admin_only", "bot.admin_help", "bot.admin_new", "bot.admin_left", "bot.admin_blocked",
            "bot.remove", "bot.add_pick", "bot.add_none", "bot.this_chat", "bot.remove_pick", "bot.remove_confirm",
            "bot.admin_removed", "bot.admin_added", "bot.list_empty", "bot.list_line", "bot.already")


def test_the_bot_speaks_all_three_languages():
    for lang in LANGS:
        s = i18n.load(lang)["strings"]
        assert [k for k in BOT_KEYS if k not in s] == [], lang
    he = Msg("bot.confirm", name="Dana", plants=["Hadera", "Ashkelon"], language="English").render("he")
    assert "Dana" in he and "Hadera" in he and "Ashkelon" in he
```

(`Msg` is `from dbw.i18n import Msg`; add the import if the file does not have it.)

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest tests/test_i18n.py -v`
Expected: FAIL listing the missing `bot.*` keys.

- [ ] **Step 3: Add the strings**

Write the three blocks below to `scratch/bot-en.json`, `scratch/bot-he.json`, `scratch/bot-ar.json` (any scratch folder outside the repo), then merge them into the `strings` object of each locale with:

```bash
for l in en he ar; do .venv/bin/python - "$l" "<scratch>/bot-$l.json" <<'EOF'
import json, sys
lang, extra = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))
path = f"dbw/locales/{lang}.json"
raw = open(path, encoding="utf-8").read()
d = json.loads(raw)
d["strings"].update(extra)
open(path, "w", encoding="utf-8", newline="\n").write(json.dumps(d, ensure_ascii=False, indent=1) + ("\n" if raw.endswith("\n") else ""))
EOF
done
for l in en he ar; do git show "HEAD:dbw/locales/$l.json" > "<scratch>/old-$l.json"; done
.venv/bin/python -c "
import json
for l in ('en', 'he', 'ar'):
    old = json.load(open(f'<scratch>/old-{l}.json', encoding='utf-8'))
    new = json.load(open(f'dbw/locales/{l}.json', encoding='utf-8'))
    assert old['meta'] == new['meta'] and old['names'] == new['names'], l
    assert all(new['strings'][k] == v for k, v in old['strings'].items()), l
print('only additions')
"
# Expected: only additions. (The raw diff always shows the last old key gaining a comma; that is fine.)
```

`bot-en.json`:
```json
{
 "bot.ask_name": "What name should the report use for you?",
 "bot.bad_name": "Please send a name of 1 to {max} characters.",
 "bot.ask_plants": "Which plants? Tap to tick, then press Done.",
 "bot.done": "Done",
 "bot.need_plant": "Tick at least one plant.",
 "bot.confirm": "Send the daily report to {name}? Plants: {plants}. Language: {language}.",
 "bot.yes": "Yes",
 "bot.no": "No",
 "bot.subscribed": "Subscribed. The report arrives every morning. Send /start to change it, or /stop to stop it.",
 "bot.cancelled": "Cancelled. Send /start to begin again.",
 "bot.menu": "Your daily report: {plants}. Language: {language}. What would you like to change?",
 "bot.change_plants": "Change plants",
 "bot.change_lang": "Change language",
 "bot.stop": "Stop the report",
 "bot.saved": "Saved.",
 "bot.stop_confirm": "Stop the daily report?",
 "bot.stopped": "Stopped. Send /start to subscribe again.",
 "bot.not_subscribed": "You are not subscribed. Send /start to subscribe.",
 "bot.removed_by_admin": "You've been removed from the daily report.",
 "bot.expired": "These buttons have expired. Send /start.",
 "bot.help": "Desal Bloom Watch sends a daily algae-risk report for seawater desalination plants.\n/start subscribe, or change your plants or language\n/stop stop the report",
 "bot.admin_only": "Only the admin can do that.",
 "bot.admin_help": "Admin: /add add someone, /remove remove someone, /list everyone.",
 "bot.admin_new": "New subscriber: {name}. {plants}. {language}.",
 "bot.admin_left": "{name} stopped the daily report.",
 "bot.admin_blocked": "{name} blocked the bot and was removed.",
 "bot.remove": "Remove",
 "bot.add_pick": "Who should get the daily report? Only chats that have messaged the bot are listed.",
 "bot.add_none": "Nobody to add: ask them to message the bot first.",
 "bot.this_chat": "This chat",
 "bot.remove_pick": "Who should be removed?",
 "bot.remove_confirm": "Remove {name}?",
 "bot.admin_removed": "{name} removed.",
 "bot.admin_added": "{name} added.",
 "bot.list_empty": "No subscribers yet.",
 "bot.list_line": "{name}: {plants} ({language})",
 "bot.already": "{name} already gets the daily report."
}
```

`bot-he.json`:
```json
{
 "bot.ask_name": "באיזה שם לפנות אליך בדוח?",
 "bot.bad_name": "נא לשלוח שם באורך 1 עד {max} תווים.",
 "bot.ask_plants": "אילו מתקנים? הקישו לסימון ואז על „סיום”.",
 "bot.done": "סיום",
 "bot.need_plant": "יש לסמן לפחות מתקן אחד.",
 "bot.confirm": "לשלוח את הדוח היומי אל {name}? מתקנים: {plants}. שפה: {language}.",
 "bot.yes": "כן",
 "bot.no": "לא",
 "bot.subscribed": "נרשמת. הדוח יגיע כל בוקר. לשינוי שלחו /start, להפסקה /stop.",
 "bot.cancelled": "בוטל. שלחו /start כדי להתחיל מחדש.",
 "bot.menu": "הדוח היומי שלך: {plants}. שפה: {language}. מה לשנות?",
 "bot.change_plants": "שינוי מתקנים",
 "bot.change_lang": "שינוי שפה",
 "bot.stop": "הפסקת הדוח",
 "bot.saved": "נשמר.",
 "bot.stop_confirm": "להפסיק את הדוח היומי?",
 "bot.stopped": "הדוח הופסק. שלחו /start כדי להירשם שוב.",
 "bot.not_subscribed": "אין לך מינוי. שלחו /start כדי להירשם.",
 "bot.removed_by_admin": "הוסרת מרשימת הדוח היומי.",
 "bot.expired": "הכפתורים האלה כבר לא בתוקף. שלחו /start.",
 "bot.help": "Desal Bloom Watch שולח דוח יומי על סיכון אצות במתקני התפלת מי ים.\n/start הרשמה, או שינוי מתקנים ושפה\n/stop הפסקת הדוח",
 "bot.admin_only": "רק המנהל יכול לעשות זאת.",
 "bot.admin_help": "ניהול: /add הוספה, /remove הסרה, /list רשימה.",
 "bot.admin_new": "מנוי חדש: {name}. {plants}. {language}.",
 "bot.admin_left": "{name} הפסיק/ה את הדוח היומי.",
 "bot.admin_blocked": "{name} חסם/ה את הבוט והוסר/ה.",
 "bot.remove": "הסרה",
 "bot.add_pick": "מי יקבל את הדוח היומי? מופיעים רק צ'אטים ששלחו הודעה לבוט.",
 "bot.add_none": "אין את מי להוסיף: בקשו מהם לשלוח הודעה לבוט קודם.",
 "bot.this_chat": "הצ'אט הזה",
 "bot.remove_pick": "את מי להסיר?",
 "bot.remove_confirm": "להסיר את {name}?",
 "bot.admin_removed": "{name} הוסר/ה.",
 "bot.admin_added": "{name} נוסף/ה.",
 "bot.list_empty": "אין עדיין מנויים.",
 "bot.list_line": "{name}: {plants} ({language})",
 "bot.already": "{name} כבר מקבל/ת את הדוח היומי."
}
```

`bot-ar.json`:
```json
{
 "bot.ask_name": "ما الاسم الذي نستخدمه لك في التقرير؟",
 "bot.bad_name": "يرجى إرسال اسم من 1 إلى {max} حرفًا.",
 "bot.ask_plants": "أي المحطات؟ اضغط للتحديد، ثم اضغط «تم».",
 "bot.done": "تم",
 "bot.need_plant": "حدّد محطة واحدة على الأقل.",
 "bot.confirm": "إرسال التقرير اليومي إلى {name}؟ المحطات: {plants}. اللغة: {language}.",
 "bot.yes": "نعم",
 "bot.no": "لا",
 "bot.subscribed": "تم الاشتراك. يصل التقرير كل صباح. أرسل /start للتغيير أو /stop للإيقاف.",
 "bot.cancelled": "تم الإلغاء. أرسل /start للبدء من جديد.",
 "bot.menu": "تقريرك اليومي: {plants}. اللغة: {language}. ماذا تريد أن تغيّر؟",
 "bot.change_plants": "تغيير المحطات",
 "bot.change_lang": "تغيير اللغة",
 "bot.stop": "إيقاف التقرير",
 "bot.saved": "تم الحفظ.",
 "bot.stop_confirm": "إيقاف التقرير اليومي؟",
 "bot.stopped": "تم الإيقاف. أرسل /start للاشتراك مجددًا.",
 "bot.not_subscribed": "أنت غير مشترك. أرسل /start للاشتراك.",
 "bot.removed_by_admin": "تمت إزالتك من قائمة التقرير اليومي.",
 "bot.expired": "انتهت صلاحية هذه الأزرار. أرسل /start.",
 "bot.help": "يرسل Desal Bloom Watch تقريرًا يوميًا عن خطر الطحالب لمحطات تحلية مياه البحر.\n/start للاشتراك أو لتغيير المحطات واللغة\n/stop لإيقاف التقرير",
 "bot.admin_only": "هذا متاح للمسؤول فقط.",
 "bot.admin_help": "المسؤول: /add إضافة، /remove إزالة، /list القائمة.",
 "bot.admin_new": "مشترك جديد: {name}. {plants}. {language}.",
 "bot.admin_left": "أوقف {name} التقرير اليومي.",
 "bot.admin_blocked": "حظر {name} البوت وتمت إزالته.",
 "bot.remove": "إزالة",
 "bot.add_pick": "من سيتلقى التقرير اليومي؟ تظهر فقط الدردشات التي راسلت البوت.",
 "bot.add_none": "لا يوجد من يمكن إضافته: اطلب منهم مراسلة البوت أولًا.",
 "bot.this_chat": "هذه الدردشة",
 "bot.remove_pick": "من تريد إزالته؟",
 "bot.remove_confirm": "إزالة {name}؟",
 "bot.admin_removed": "تمت إزالة {name}.",
 "bot.admin_added": "تمت إضافة {name}.",
 "bot.list_empty": "لا يوجد مشتركون بعد.",
 "bot.list_line": "{name}: {plants} ({language})",
 "bot.already": "{name} يتلقى التقرير اليومي بالفعل."
}
```

- [ ] **Step 4: Run the i18n tests**

Run: `.venv/bin/python -m pytest tests/test_i18n.py tests/test_report_i18n.py -v`
Expected: PASS (parity, placeholders and Western digits hold).

- [ ] **Step 5: Commit**

```bash
git add dbw/locales tests/test_i18n.py
git commit -m "locales: sign-up bot wording in en, he, ar"
```

---

### Task 5: The bot — sign up, change, stop, help

**Files:**
- Create: `dbw/bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: Task 2 `subscribers.*`; Task 3 `telegram.send_message / send_buttons / edit_buttons / answer_callback / chat_name / TelegramError`; Task 4 `bot.*` keys; `registry.load()` boxes (`.id`, `.kind == "plant"`, `.name`); `i18n.display_name(lang, id, fallback)`.
- Produces: `class Bot(conn, token, admin_ids, admin_lang="en", boxes=None, log=print)` with `handle(update: dict) -> None`; constants `CHANNEL = "telegram"`, `LANG_PROMPT`, `FLOWS`. Task 6 adds the admin methods (`admin_add`, `admin_list`, `admin_remove`, `admin_pick`, `admin_button`) to this class; Task 7 adds `poll_once`.

**Conversation model.** One row in `conversations` per chat: `step` is the question now open, `data` holds `flow` (which questionnaire), `ui` (the language questions are worded in), and the answers so far (`lang`, `name`, `picked`, and for the admin flow `target`). Buttons carry `kind:arg` data: `lang:he`, `p:hadera`, `p:done`, `ok:yes|no`, `m:plants|lang|stop`, `stop:yes|no`, `add:<address>|here`, `rm:<id>`, `rmok:<id>`, `rmno`. A stateful button is accepted only when the chat's open step is the one it answers; anything else gets the "expired" toast.

| Flow | Steps | Ends |
|---|---|---|
| `self` (new person, private chat) | lang → name → plants → confirm | `ok:yes` subscribes, admins notified with [Remove] |
| `admin` (admin adding a contact or group) | plants → lang → confirm | `ok:yes` subscribes the target, target told |
| `plants` / `lang` (subscriber changing) | plants / lang | saved at once |
| `menu`, `stop`, `add` | one step each | handled by their buttons |

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot.py`:

```python
"""dbw/bot.py: people signing up, changing and stopping, through fake Telegram updates. Offline."""
import json

import pytest

from dbw import bot as botmod, i18n, store, subscribers as subs
from dbw.i18n import Msg
from test_telegram import TOKEN, Http, http  # noqa: F401  (http is a fixture)

ADMIN = 999
DANA = 111


def msg(text, chat=DANA, user=None, type="private", name="Dana"):
    chat_obj = {"id": chat, "type": type, **({"first_name": name} if type == "private" else {"title": name})}
    return {"update_id": 0, "message": {"message_id": 1, "date": 1790000000, "text": text, "chat": chat_obj,
                                        "from": {"id": chat if user is None else user, "first_name": name}}}


def tap(data, chat=DANA, user=None, text="question"):
    return {"update_id": 0, "callback_query": {"id": "cb", "data": data, "from": {"id": chat if user is None else user},
                                               "message": {"message_id": 7, "chat": {"id": chat}, "text": text}}}


def calls(http, method=None):
    """[(method, body as dict)] of every JSON call, optionally only one method."""
    return [(c.method, json.loads(c.body)) for c in http.calls if method in (None, c.method)]


def last_text(http, chat=DANA):
    return [b["text"] for m, b in calls(http) if m in ("sendMessage", "editMessageText") and b["chat_id"] == str(chat)][-1]


def buttons(body):
    return [b["callback_data"] for row in body["reply_markup"]["inline_keyboard"] for b in row]


def toast(http):
    return calls(http, "answerCallbackQuery")[-1][1].get("text", "")


def sent(http):
    """The body of the last sendMessage (a button press also answers the callback, so it is not the last call)."""
    return calls(http, "sendMessage")[-1][1]


def t(lang, code, **kw):
    return Msg(code, **kw).render(lang)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "t.sqlite"


@pytest.fixture
def b(path, http):
    return botmod.Bot(store.connect(path), TOKEN, admin_ids=[ADMIN], admin_lang="en", log=lambda m: None)


def sign_up(b, lang="he", name="Dana", plants=("hadera", "ashkelon"), chat=DANA):
    for u in (msg("/start", chat, name=name), tap(f"lang:{lang}", chat), msg(name, chat, name=name),
              *[tap(f"p:{p}", chat) for p in plants], tap("p:done", chat), tap("ok:yes", chat)):
        b.handle(u)


# --- a new person ---------------------------------------------------------------------------------------------

def test_a_new_person_signs_up_step_by_step(b, http):
    b.handle(msg("/start"))
    body = sent(http)
    assert body["text"] == botmod.LANG_PROMPT and buttons(body) == ["lang:en", "lang:he", "lang:ar"]
    b.handle(tap("lang:he"))
    assert last_text(http) == t("he", "bot.ask_name")
    b.handle(msg("  Dana   L "))
    body = sent(http)
    assert body["text"] == t("he", "bot.ask_plants") and "p:hadera" in buttons(body) and buttons(body)[-1] == "p:done"
    b.handle(tap("p:ashkelon"))
    b.handle(tap("p:hadera"))
    method, body = calls(http, "editMessageText")[-1]
    assert body["message_id"] == 7
    ticked = [x["text"] for row in body["reply_markup"]["inline_keyboard"] for x in row if x["text"].startswith("✅")]
    assert len(ticked) == 2
    b.handle(tap("p:done"))
    body = sent(http)
    assert buttons(body) == ["ok:yes", "ok:no"] and "Dana L" in body["text"]
    b.handle(tap("ok:yes"))
    (s,) = subs.active(b.conn)
    assert (s.name, s.address, s.plants, s.language, s.added_by) == ("Dana L", "111", ("hadera", "ashkelon"), "he", "self")
    assert t("he", "bot.subscribed") in [x["text"] for _, x in calls(http, "sendMessage") if x["chat_id"] == "111"]
    (note,) = [x for _, x in calls(http, "sendMessage") if x["chat_id"] == str(ADMIN)]
    assert note["text"].startswith("New subscriber: Dana L.") and buttons(note) == [f"rm:{s.id}"]
    assert subs.get_conversation(b.conn, "telegram", "111") is None


def test_plants_are_stored_in_registry_order_whatever_the_tap_order(b):
    sign_up(b, plants=("eilat", "hadera"))
    assert subs.active(b.conn)[0].plants == ("hadera", "eilat")


def test_the_questionnaire_survives_a_restart(b, path, http):
    b.handle(msg("/start"))
    b.handle(tap("lang:ar"))
    again = botmod.Bot(store.connect(path), TOKEN, admin_ids=[ADMIN], log=lambda m: None)
    again.handle(msg("Dana"))
    assert sent(http)["text"] == t("ar", "bot.ask_plants")


def test_done_with_nothing_ticked_is_refused_with_a_toast(b, http):
    for u in (msg("/start"), tap("lang:en"), msg("Dana"), tap("p:done")):
        b.handle(u)
    assert toast(http) == t("en", "bot.need_plant")
    assert subs.get_conversation(b.conn, "telegram", "111")[0] == "plants"


@pytest.mark.parametrize("bad", ["", "x" * 65, "/whatever"])
def test_a_bad_name_is_asked_again(b, http, bad):
    for u in (msg("/start"), tap("lang:en"), msg(bad)):
        b.handle(u)
    assert last_text(http) == t("en", "bot.bad_name", max=64)
    assert subs.get_conversation(b.conn, "telegram", "111")[0] == "name"


def test_no_at_the_end_cancels(b, http):
    for u in (msg("/start"), tap("lang:en"), msg("Dana"), tap("p:hadera"), tap("p:done"), tap("ok:no")):
        b.handle(u)
    assert subs.active(b.conn) == [] and last_text(http) == t("en", "bot.cancelled")


def test_an_old_button_is_expired_and_changes_nothing(b, http):
    b.handle(tap("p:hadera"))
    assert toast(http) == t("en", "bot.expired") and subs.active(b.conn) == []
    b.handle(msg("/start"))
    b.handle(tap("ok:yes"))  # a confirm button while the language question is open
    assert toast(http) == t("en", "bot.expired") and subs.active(b.conn) == []


def test_typing_while_buttons_are_open_asks_the_question_again(b, http):
    b.handle(msg("/start"))
    b.handle(msg("hello?"))
    assert sent(http)["text"] == botmod.LANG_PROMPT


def test_every_message_records_its_chat_as_a_contact(b):
    b.handle(msg("hi", chat=-100222, user=5, type="supergroup", name="Plant ops"))
    assert subs.contacts(b.conn)[0] == {"address": "-100222", "name": "Plant ops", "type": "supergroup", "last": 1790000000}


def test_a_group_member_starting_the_bot_gets_no_questionnaire(b, http):
    b.handle(msg("/start", chat=-100222, user=5, type="supergroup", name="Plant ops"))
    assert http.calls == [] and subs.get_conversation(b.conn, "telegram", "-100222") is None


def test_a_message_with_no_chat_is_ignored(b, http):
    b.handle({"update_id": 3, "edited_message": {"text": "x"}})
    b.handle({"update_id": 4, "poll": {"id": "p"}})
    assert http.calls == []


# --- a subscriber -----------------------------------------------------------------------------------------------

def test_start_again_shows_the_menu(b, http):
    sign_up(b)
    b.handle(msg("/start"))
    body = sent(http)
    assert buttons(body) == ["m:plants", "m:lang", "m:stop"]
    assert body["text"] == t("he", "bot.menu", plants=["חדרה", "אשקלון"], language="עברית")


def test_a_subscriber_changes_plants(b, http):
    sign_up(b)
    for u in (msg("/start"), tap("m:plants"), tap("p:ashkelon"), tap("p:eilat"), tap("p:done")):
        b.handle(u)
    assert subs.active(b.conn)[0].plants == ("hadera", "eilat") and last_text(http) == t("he", "bot.saved")


def test_a_subscriber_changes_language_and_hears_back_in_the_new_one(b, http):
    sign_up(b)
    for u in (msg("/start"), tap("m:lang"), tap("lang:en")):
        b.handle(u)
    assert subs.active(b.conn)[0].language == "en" and last_text(http) == t("en", "bot.saved")


@pytest.mark.parametrize("how", [[msg("/stop")], [msg("stop")], [msg("STOP")], [msg("/remove")],
                                 [msg("/start"), tap("m:stop")]])
def test_stop_asks_first_then_removes_and_tells_the_admin(b, http, how):
    sign_up(b)
    for u in how:
        b.handle(u)
    body = sent(http)
    assert body["text"] == t("he", "bot.stop_confirm") and buttons(body) == ["stop:yes", "stop:no"]
    b.handle(tap("stop:yes"))
    assert subs.active(b.conn) == [] and last_text(http) == t("he", "bot.stopped")
    assert sent(http) == {"chat_id": str(ADMIN), "text": "Dana stopped the daily report."}


def test_stop_no_keeps_the_subscription(b, http):
    sign_up(b)
    b.handle(msg("/stop"))
    b.handle(tap("stop:no"))
    assert len(subs.active(b.conn)) == 1


def test_stop_when_not_subscribed_says_so(b, http):
    b.handle(msg("/stop"))
    assert last_text(http) == t("en", "bot.not_subscribed")


def test_help_is_in_the_persons_language_and_the_admin_also_sees_admin_help(b, http):
    sign_up(b, lang="ar")
    b.handle(msg("/help"))
    assert last_text(http) == t("ar", "bot.help")
    b.handle(msg("/help", chat=ADMIN))
    assert last_text(http, ADMIN) == t("en", "bot.help") + "\n\n" + t("en", "bot.admin_help")


def test_a_failed_admin_notification_does_not_undo_the_sign_up(path, http):
    from test_telegram import fail
    logged = []
    b = botmod.Bot(store.connect(path), TOKEN, admin_ids=[ADMIN], log=logged.append)
    for u in (msg("/start"), tap("lang:en"), msg("Dana"), tap("p:hadera"), tap("p:done")):
        b.handle(u)
    http.script = [(200, {"ok": True, "result": {}}), fail(403, "Forbidden: bot can't initiate conversation")]
    b.handle(tap("ok:yes"))
    assert len(subs.active(b.conn)) == 1 and any("admin 999" in line for line in logged)
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_bot.py -v`
Expected: FAIL with `ImportError: cannot import name 'bot' from 'dbw'`.

- [ ] **Step 3: Implement `dbw/bot.py` (conversations part)**

```python
"""`dbw bot`: the Telegram sign-up bot. It answers people who message it (sign up, change plants or language, stop)
and the admin (/add, /remove, /list). It never sends the daily report: `dbw run` does. All state lives in the
database (dbw/subscribers.py), so a restart loses nobody's place. All Telegram access goes through
dbw/channels/telegram.py, whose `_http` is the one seam the tests replace."""
from dbw import i18n, registry, subscribers
from dbw.channels import telegram
from dbw.i18n import Msg

CHANNEL = "telegram"
LANG_PROMPT = "Choose a language · בחרו שפה · اختر اللغة"  # asked before we know which language to ask in
FLOWS = {
    "self": ("lang", "name", "plants", "confirm"),  # a new person, in a private chat
    "admin": ("plants", "lang", "confirm"),  # the admin adding a contact or a group (the name comes from contacts)
    "plants": ("plants",),  # a subscriber changing plants
    "lang": ("lang",),  # a subscriber changing language
}
BUTTON_STEP = {"lang": "lang", "p": "plants", "ok": "confirm", "m": "menu", "stop": "stop", "add": "add"}
ADMIN_FLOWS = ("admin", "add")
STOP_WORDS = ("/stop", "/remove", "stop")


class BotError(Exception):
    """One plain line: the bot cannot start."""


class Bot:
    def __init__(self, conn, token, admin_ids, admin_lang=i18n.DEFAULT, boxes=None, log=print):
        self.conn, self.token, self.log = conn, token, log
        self.admins = {int(a) for a in admin_ids}
        self.admin_lang = admin_lang
        self.plant_boxes = [b for b in (boxes if boxes is not None else registry.load()) if b.kind == "plant"]
        self.plant_ids = [b.id for b in self.plant_boxes]

    # --- words and state -------------------------------------------------------------------------------------

    def t(self, lang, code, **params):
        return Msg(code, **params).render(lang)

    def names(self, lang, plant_ids):
        """Display names of `plant_ids` in `lang`, in registry order."""
        return [i18n.display_name(lang, b.id, b.name or b.id) for b in self.plant_boxes if b.id in plant_ids]

    def lang_name(self, lang):
        return i18n.load(lang)["meta"]["name"]

    def sub(self, chat_id):
        return subscribers.get_active(self.conn, CHANNEL, str(chat_id))

    def lang_of(self, chat_id, user_id=None):
        """The language to answer this chat in: its subscription's, else an open self sign-up's, else the admin's
        (for the admin), else English."""
        s = self.sub(chat_id)
        if s:
            return s.language
        step, data = self.load(chat_id)
        if step and data.get("flow") not in ADMIN_FLOWS:
            return data.get("ui", i18n.DEFAULT)
        return self.admin_lang if user_id in self.admins else i18n.DEFAULT

    def load(self, chat_id):
        return subscribers.get_conversation(self.conn, CHANNEL, str(chat_id)) or (None, {})

    def save(self, chat_id, step, data):
        subscribers.set_conversation(self.conn, CHANNEL, str(chat_id), step, data)

    def end(self, chat_id):
        subscribers.clear_conversation(self.conn, CHANNEL, str(chat_id))

    def say(self, chat_id, text):
        telegram.send_message(self.token, chat_id, text)

    def ask(self, chat_id, text, rows):
        telegram.send_buttons(self.token, chat_id, text, rows)

    def tell(self, chat_id, text, rows=None):
        """Message someone other than the chat being answered; a failure (they blocked the bot, never opened it)
        is logged, never raised."""
        try:
            self.ask(chat_id, text, rows) if rows else self.say(chat_id, text)
        except telegram.TelegramError as e:
            self.log(f"chat {chat_id}: not told ({e})")

    def notify_admins(self, code, sub_id=None, **params):
        for a in sorted(self.admins):
            lang = self.lang_of(a, a)
            rows = [[(self.t(lang, "bot.remove"), f"rm:{sub_id}")]] if sub_id else None
            try:
                self.ask(a, self.t(lang, code, **params), rows) if rows else self.say(a, self.t(lang, code, **params))
            except telegram.TelegramError as e:
                self.log(f"admin {a}: not told ({e})")

    # --- questions ----------------------------------------------------------------------------------------------

    def lang_rows(self):
        return [[(self.lang_name(l), f"lang:{l}") for l in i18n.LANGUAGES]]

    def plant_rows(self, lang, picked):
        rows = [[(("✅ " if b.id in picked else "▫️ ") + i18n.display_name(lang, b.id, b.name or b.id), f"p:{b.id}")]
                for b in self.plant_boxes]
        return rows + [[(self.t(lang, "bot.done"), "p:done")]]

    def yes_no(self, lang, kind):
        return [[(self.t(lang, "bot.yes"), f"{kind}:yes"), (self.t(lang, "bot.no"), f"{kind}:no")]]

    def prompt(self, cid, step, data):
        """Remember `step` as the open question and send it."""
        self.save(cid, step, data)
        ui = data.get("ui", i18n.DEFAULT)
        if step == "lang":
            return self.ask(cid, LANG_PROMPT, self.lang_rows())
        if step == "name":
            return self.say(cid, self.t(ui, "bot.ask_name"))
        if step == "plants":
            return self.ask(cid, self.t(ui, "bot.ask_plants"), self.plant_rows(ui, data["picked"]))
        if step == "confirm":
            text = self.t(ui, "bot.confirm", name=data["name"], plants=self.names(ui, data["picked"]),
                          language=self.lang_name(data["lang"]))
            return self.ask(cid, text, self.yes_no(ui, "ok"))
        if step == "menu":
            s = self.sub(cid)
            if s is None:  # removed while the menu was open
                self.end(cid)
                return self.start(cid)
            text = self.t(ui, "bot.menu", plants=self.names(ui, s.plants), language=self.lang_name(s.language))
            return self.ask(cid, text, [[(self.t(ui, "bot.change_plants"), "m:plants")],
                                        [(self.t(ui, "bot.change_lang"), "m:lang")], [(self.t(ui, "bot.stop"), "m:stop")]])
        if step == "stop":
            return self.ask(cid, self.t(ui, "bot.stop_confirm"), self.yes_no(ui, "stop"))
        raise ValueError(f"no question for step {step!r}")

    def advance(self, cid, data, step):
        """The next question of the flow, or, at the end of a change flow, save it."""
        flow = FLOWS[data["flow"]]
        i = flow.index(step) + 1
        if i < len(flow):
            return self.prompt(cid, flow[i], data)
        s = self.sub(cid)
        self.end(cid)
        if s is None:
            return self.say(cid, self.t(data["ui"], "bot.not_subscribed"))
        if data["flow"] == "plants":
            subscribers.update(self.conn, s.id, plants=data["picked"])
            return self.say(cid, self.t(s.language, "bot.saved"))
        subscribers.update(self.conn, s.id, language=data["lang"])
        self.say(cid, self.t(data["lang"], "bot.saved"))

    # --- messages -----------------------------------------------------------------------------------------------

    def handle(self, update):
        """Answer one Telegram update. Updates that are neither a message with a chat nor a button press are ignored."""
        if isinstance(update.get("callback_query"), dict):
            return self.on_button(update["callback_query"])
        msg = update.get("message")
        if not isinstance(msg, dict) or not isinstance(msg.get("chat"), dict) or "id" not in msg["chat"]:
            return
        chat = msg["chat"]
        cid, user = chat["id"], (msg.get("from") or {}).get("id")
        subscribers.touch_contact(self.conn, CHANNEL, cid, telegram.chat_name(chat) or str(cid), chat.get("type", ""),
                                  msg.get("date") or 0)
        text = (msg.get("text") or "").strip()
        cmd = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
        admin = user in self.admins
        if cmd == "/help":
            lang = self.lang_of(cid, user)
            return self.say(cid, self.t(lang, "bot.help") + ("\n\n" + self.t(lang, "bot.admin_help") if admin else ""))
        if cmd in ("/add", "/list") or (cmd == "/remove" and admin):
            if not admin:
                return self.say(cid, self.t(self.lang_of(cid, user), "bot.admin_only"))
            return {"/add": self.admin_add, "/list": self.admin_list, "/remove": self.admin_remove}[cmd](chat, user)
        if chat.get("type") != "private":
            return  # in a group the bot answers /help and the admin's commands only
        if cmd == "/start":
            return self.start(cid)
        if cmd in STOP_WORDS or text.lower() in STOP_WORDS:
            return self.ask_stop(cid)
        step, data = self.load(cid)
        if step == "name":
            return self.take_name(cid, text, data)
        if step in ("lang", "plants", "confirm", "menu", "stop"):
            return self.prompt(cid, step, data)  # typed while buttons are open: ask again
        self.end(cid)
        self.start(cid)

    def start(self, cid):
        s = self.sub(cid)
        if s:
            return self.prompt(cid, "menu", {"flow": "menu", "ui": s.language})
        self.prompt(cid, "lang", {"flow": "self", "ui": i18n.DEFAULT, "picked": []})

    def ask_stop(self, cid):
        s = self.sub(cid)
        if s is None:
            lang = self.lang_of(cid)
            self.end(cid)
            return self.say(cid, self.t(lang, "bot.not_subscribed"))
        self.prompt(cid, "stop", {"flow": "stop", "ui": s.language})

    def take_name(self, cid, text, data):
        try:
            if text.startswith("/"):
                raise ValueError("a command is not a name")
            name = subscribers.clean_name(text)
        except ValueError:
            return self.say(cid, self.t(data["ui"], "bot.bad_name", max=subscribers.NAME_MAX))
        self.advance(cid, {**data, "name": name}, "name")

    # --- buttons ------------------------------------------------------------------------------------------------

    def on_button(self, cq):
        msg = cq.get("message") or {}
        cid = (msg.get("chat") or {}).get("id")
        user = (cq.get("from") or {}).get("id")
        kind, _, arg = (cq.get("data") or "").partition(":")
        note = ""
        try:
            if cid is None:
                note = self.t(i18n.DEFAULT, "bot.expired")
            elif kind in ("rm", "rmok", "rmno"):
                note = self.admin_button(cid, user, kind, arg)
            else:
                note = self.step_button(cid, user, kind, arg, msg)
        finally:
            telegram.answer_callback(self.token, cq.get("id", ""), note or "")

    def step_button(self, cid, user, kind, arg, msg):
        """A button that answers the chat's open question. -> a toast ('' for none)."""
        step, data = self.load(cid)
        if step is None or BUTTON_STEP.get(kind) != step or (data.get("flow") in ADMIN_FLOWS and user not in self.admins):
            return self.t(self.lang_of(cid, user), "bot.expired")
        ui = data["ui"]
        if kind == "lang":
            if arg not in i18n.LANGUAGES:
                return self.t(ui, "bot.expired")
            data = {**data, "lang": arg, **({"ui": arg} if data["flow"] == "self" else {})}
            self.advance(cid, data, "lang")
        elif kind == "p":
            if arg == "done":
                if not data["picked"]:
                    return self.t(ui, "bot.need_plant")
                self.advance(cid, data, "plants")
            elif arg in self.plant_ids:
                picked = [p for p in self.plant_ids if (p in data["picked"]) != (p == arg)]
                self.save(cid, "plants", {**data, "picked": picked})
                telegram.edit_buttons(self.token, cid, msg.get("message_id"), msg.get("text") or self.t(ui, "bot.ask_plants"),
                                      self.plant_rows(ui, picked))
        elif kind == "ok":
            self.end(cid)
            if arg == "yes":
                self.subscribe(cid, data)
            else:
                self.say(cid, self.t(ui, "bot.cancelled"))
        elif kind == "m":
            s = self.sub(cid)
            if s is None:
                self.end(cid)
                return self.t(ui, "bot.not_subscribed")
            if arg == "plants":
                self.prompt(cid, "plants", {"flow": "plants", "ui": s.language, "picked": list(s.plants)})
            elif arg == "lang":
                self.prompt(cid, "lang", {"flow": "lang", "ui": s.language})
            else:
                self.ask_stop(cid)
        elif kind == "stop":
            self.end(cid)
            s = self.sub(cid)
            if arg != "yes" or s is None:
                self.say(cid, self.t(ui, "bot.cancelled"))
            else:
                subscribers.remove(self.conn, s.id)
                self.say(cid, self.t(s.language, "bot.stopped"))
                self.notify_admins("bot.admin_left", name=s.name)
        elif kind == "add":
            return self.admin_pick(cid, data, arg)
        return ""

    def subscribe(self, cid, data):
        target = data.get("target", str(cid))
        by_admin = data["flow"] == "admin"
        try:
            s = subscribers.add(self.conn, data["name"], CHANNEL, target, data["picked"], data["lang"],
                                "admin" if by_admin else "self")
        except ValueError:  # subscribed meanwhile: a double tap, or the admin added them
            return self.say(cid, self.t(data["ui"], "bot.already", name=data["name"]))
        if by_admin:
            self.say(cid, self.t(data["ui"], "bot.admin_added", name=s.name))
            if target != str(cid):
                self.end(target)  # an unfinished sign-up of theirs is now moot
                self.tell(target, self.t(s.language, "bot.subscribed"))
            return
        self.say(cid, self.t(s.language, "bot.subscribed"))
        self.notify_admins("bot.admin_new", sub_id=s.id, name=s.name, plants=self.names(self.admin_lang, s.plants),
                           language=self.lang_name(s.language))

    # --- admin (Task 6) -----------------------------------------------------------------------------------------

    def admin_add(self, chat, user):
        raise NotImplementedError

    admin_list = admin_remove = admin_add

    def admin_pick(self, cid, data, arg):
        raise NotImplementedError

    def admin_button(self, cid, user, kind, arg):
        raise NotImplementedError
```

Note the `notify_admins` "New subscriber" text uses `self.admin_lang` for plant names; when an admin is also a subscriber in another language the names stay in `admin_lang` (acceptable; the whole line is short).

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bot.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dbw/bot.py tests/test_bot.py
git commit -m "bot: sign up, change plants or language, stop, help"
```

---

### Task 6: The bot — admin commands

**Files:**
- Modify: `dbw/bot.py` (replace the four Task 5 stubs)
- Test: `tests/test_bot_admin.py`

**Interfaces:**
- Consumes: Task 5 `Bot` helpers (`t`, `names`, `lang_name`, `lang_of`, `sub`, `save`, `end`, `say`, `ask`, `tell`, `prompt`, `yes_no`), `subscribers.active / get / remove / contacts`.
- Produces: `Bot.admin_add(chat, user)`, `Bot.admin_list(chat, user)`, `Bot.admin_remove(chat, user)`, `Bot.admin_pick(cid, data, arg) -> str`, `Bot.admin_button(cid, user, kind, arg) -> str`; `ADD_LIST_MAX = 30`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_admin.py`:

```python
"""dbw/bot.py: the admin's /add, /remove, /list and the [Remove] button. Offline."""
import pytest

from dbw import subscribers as subs
from test_bot import ADMIN, DANA, b, buttons, calls, last_text, msg, path, sent, sign_up, t, tap, toast  # noqa: F401
from test_telegram import http  # noqa: F401

GROUP = -100222


@pytest.mark.parametrize("cmd", ["/add", "/list"])
def test_admin_commands_are_refused_to_others(b, http, cmd):
    b.handle(msg(cmd))
    assert last_text(http) == t("en", "bot.admin_only")


def test_list_shows_everyone_or_says_nobody(b, http):
    b.handle(msg("/list", chat=ADMIN))
    assert last_text(http, ADMIN) == t("en", "bot.list_empty")
    sign_up(b, lang="he", name="Dana", plants=("hadera",))
    sign_up(b, lang="en", name="Avi", plants=("ashkelon",), chat=222)
    b.handle(msg("/list", chat=ADMIN))
    assert last_text(http, ADMIN) == "Avi: Ashkelon (English)\nDana: Hadera (עברית)"  # English names: plants.yaml


def test_admin_adds_a_contact_who_is_then_told(b, http):
    b.handle(msg("hello", chat=333, name="Noa"))  # Noa messaged the bot once
    b.handle(msg("/add", chat=ADMIN))
    assert buttons(sent(http)) == ["add:here", "add:333"]  # "This chat" (the admin), then Noa; not the admin twice
    for u in (tap("add:333", chat=ADMIN), tap("p:ashkelon", chat=ADMIN), tap("p:done", chat=ADMIN)):
        b.handle(u)
    assert sent(http)["text"] == "Choose a language · בחרו שפה · اختر اللغة"
    b.handle(tap("lang:he", chat=ADMIN))
    assert last_text(http, ADMIN) == t("en", "bot.confirm", name="Noa", plants=["Ashkelon"], language="עברית")
    b.handle(tap("ok:yes", chat=ADMIN))
    (s,) = subs.active(b.conn)
    assert (s.address, s.name, s.plants, s.language, s.added_by) == ("333", "Noa", ("ashkelon",), "he", "admin")
    assert last_text(http, ADMIN) == t("en", "bot.admin_added", name="Noa")
    assert last_text(http, 333) == t("he", "bot.subscribed")
    assert subs.get_conversation(b.conn, "telegram", "333") is None  # her own "hello" sign-up is closed


def test_admin_adds_a_group_from_inside_it(b, http):
    b.handle(msg("/add", chat=GROUP, user=ADMIN, type="supergroup", name="Plant ops"))
    assert buttons(sent(http))[0] == "add:here"
    for u in (tap("add:here", chat=GROUP, user=ADMIN), tap("p:hadera", chat=GROUP, user=ADMIN),
              tap("p:done", chat=GROUP, user=ADMIN), tap("lang:en", chat=GROUP, user=ADMIN),
              tap("ok:yes", chat=GROUP, user=ADMIN)):
        b.handle(u)
    (s,) = subs.active(b.conn)
    assert (s.address, s.name) == (str(GROUP), "Plant ops")


def test_a_group_member_cannot_use_the_admins_buttons(b, http):
    b.handle(msg("/add", chat=GROUP, user=ADMIN, type="supergroup", name="Plant ops"))
    b.handle(tap("add:here", chat=GROUP, user=5))
    assert toast(http) == t("en", "bot.expired") and subs.get_conversation(b.conn, "telegram", str(GROUP))[0] == "add"


def test_add_lists_nobody_already_subscribed(b, http):
    sign_up(b)
    b.handle(msg("/add", chat=ADMIN))
    assert "add:111" not in buttons(sent(http))


def test_adding_someone_already_subscribed_says_so(b, http):
    b.handle(msg("hi", chat=333, name="Noa"))
    b.handle(msg("/add", chat=ADMIN))
    sign_up(b, chat=333, name="Noa")  # Noa signs up herself while the admin's list is open
    b.handle(tap("add:333", chat=ADMIN))
    assert last_text(http, ADMIN) == t("en", "bot.already", name="Noa")


def test_remove_asks_then_removes_and_tells_the_person(b, http):
    sign_up(b)
    s = subs.active(b.conn)[0]
    b.handle(msg("/remove", chat=ADMIN))
    assert buttons(sent(http)) == [f"rm:{s.id}"]
    b.handle(tap(f"rm:{s.id}", chat=ADMIN))
    assert buttons(sent(http)) == [f"rmok:{s.id}", "rmno"]
    b.handle(tap(f"rmok:{s.id}", chat=ADMIN))
    assert subs.active(b.conn) == []
    assert last_text(http, DANA) == t("he", "bot.removed_by_admin")
    assert last_text(http, ADMIN) == t("en", "bot.admin_removed", name="Dana")


def test_the_remove_button_on_the_new_subscriber_note_works(b, http):
    sign_up(b)
    s = subs.active(b.conn)[0]
    b.handle(tap(f"rm:{s.id}", chat=ADMIN))
    b.handle(tap(f"rmok:{s.id}", chat=ADMIN))
    assert subs.active(b.conn) == []


def test_a_stale_remove_button_is_expired(b, http):
    sign_up(b)
    s = subs.active(b.conn)[0]
    b.handle(msg("/stop"))
    b.handle(tap("stop:yes"))
    b.handle(tap(f"rmok:{s.id}", chat=ADMIN))
    assert toast(http) == t("en", "bot.expired")


def test_only_the_admin_can_press_remove(b, http):
    sign_up(b)
    s = subs.active(b.conn)[0]
    b.handle(tap(f"rmok:{s.id}", chat=DANA))
    assert len(subs.active(b.conn)) == 1 and toast(http) == t("he", "bot.admin_only")


def test_remove_with_nobody_subscribed(b, http):
    b.handle(msg("/remove", chat=ADMIN))
    assert last_text(http, ADMIN) == t("en", "bot.list_empty")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_bot_admin.py -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement**

In `dbw/bot.py`, add `ADD_LIST_MAX = 30  # contacts offered by /add, newest first (a longer keyboard is unusable)` next to the constants, and replace the Task 5 admin stubs with:

```python
    # --- admin --------------------------------------------------------------------------------------------------

    def admin_list(self, chat, user):
        lang = self.lang_of(chat["id"], user)
        lines = sorted(self.t(lang, "bot.list_line", name=s.name, plants=self.names(lang, s.plants),
                              language=self.lang_name(s.language)) for s in subscribers.active(self.conn))
        self.say(chat["id"], "\n".join(lines) or self.t(lang, "bot.list_empty"))

    def admin_add(self, chat, user):
        """Offer 'This chat' (a group, or the admin themselves) and the contacts not yet subscribed."""
        cid, lang = chat["id"], self.lang_of(chat["id"], user)
        taken = {s.address for s in subscribers.active(self.conn)}
        rows = [[(self.t(lang, "bot.this_chat"), "add:here")]] if str(cid) not in taken else []
        others = [c for c in subscribers.contacts(self.conn) if c["address"] not in taken and c["address"] != str(cid)]
        rows += [[(c["name"], f"add:{c['address']}")] for c in others[:ADD_LIST_MAX]]
        if not rows:
            return self.say(cid, self.t(lang, "bot.add_none"))
        self.save(cid, "add", {"flow": "add", "ui": lang})
        self.ask(cid, self.t(lang, "bot.add_pick"), rows)

    def admin_pick(self, cid, data, arg):
        address = str(cid) if arg == "here" else arg
        contact = next((c for c in subscribers.contacts(self.conn) if c["address"] == address), None)
        if contact is None:
            self.end(cid)
            return self.t(data["ui"], "bot.expired")
        if self.sub(address):
            self.end(cid)
            self.say(cid, self.t(data["ui"], "bot.already", name=contact["name"]))
            return ""
        self.prompt(cid, "plants", {"flow": "admin", "ui": data["ui"], "target": address, "name": contact["name"],
                                    "picked": []})
        return ""

    def admin_remove(self, chat, user):
        cid, lang = chat["id"], self.lang_of(chat["id"], user)
        subs = subscribers.active(self.conn)
        if not subs:
            return self.say(cid, self.t(lang, "bot.list_empty"))
        self.ask(cid, self.t(lang, "bot.remove_pick"), [[(s.name, f"rm:{s.id}")] for s in subs])

    def admin_button(self, cid, user, kind, arg):
        """rm:<id> asks to confirm, rmok:<id> removes, rmno cancels. Stateless: the id travels on the button."""
        lang = self.lang_of(cid, user)
        if user not in self.admins:
            return self.t(lang, "bot.admin_only")
        if kind == "rmno":
            self.say(cid, self.t(lang, "bot.cancelled"))
            return ""
        s = subscribers.get(self.conn, int(arg)) if arg.isdigit() else None
        if s is None or s.status != subscribers.ACTIVE:
            return self.t(lang, "bot.expired")
        if kind == "rm":
            self.ask(cid, self.t(lang, "bot.remove_confirm", name=s.name),
                     [[(self.t(lang, "bot.yes"), f"rmok:{s.id}"), (self.t(lang, "bot.no"), "rmno")]])
            return ""
        subscribers.remove(self.conn, s.id)
        self.tell(s.address, self.t(s.language, "bot.removed_by_admin"))
        self.say(cid, self.t(lang, "bot.admin_removed", name=s.name))
        return ""
```

English plant names come from `plants.yaml` (`hadera` → "Hadera", `ashkelon` → "Ashkelon"); the tests avoid `eilat`, whose English name is long.

- [ ] **Step 4: Run the bot tests**

Run: `.venv/bin/python -m pytest tests/test_bot.py tests/test_bot_admin.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dbw/bot.py tests/test_bot_admin.py
git commit -m "bot: admin /add, /remove, /list and the Remove button"
```

---

### Task 7: The bot loop — `dbw bot run`

**Files:**
- Modify: `dbw/bot.py` (poll loop, lock, log)
- Modify: `dbw/cli.py` (`bot` subcommand, `run` action only; Task 8 adds install/uninstall/status)
- Test: `tests/test_bot_runtime.py`

**Interfaces:**
- Consumes: `telegram.get_updates(token, offset, timeout)`, `telegram.LONG_POLL`, `subscribers.get_state / set_state`, `config.telegram_admin_ids`, `config.report_language`, `cli._telegram_token(config_path)`.
- Produces: `OFFSET_KEY = "telegram_offset"`, `ERROR_WAIT = 5`; `Bot.poll_once() -> int` (updates handled); `run(bot, log, stop=lambda: False, sleep=time.sleep)`; `lock_path() -> Path` (`store.default_path().parent / "dbw-bot.lock"`); `acquire_lock(path)` (returns a lock object with `close()`; raises `BotError` when another bot holds it); `lock_held(path) -> bool`; `file_log(path, token) -> callable`; CLI `dbw bot [run] [--log FILE] [--config FILE]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_runtime.py`:

```python
"""dbw/bot.py runtime: the long-poll loop, the saved offset, the single-instance lock, the log, `dbw bot run`.
Offline: Telegram is the fake `_http`."""
import http.client as httpclient
import json
import sqlite3

import pytest

from dbw import bot as botmod, cli, config, registry, store, subscribers as subs
from test_bot import msg
from test_telegram import TOKEN, Http, fail, http  # noqa: F401


def updates(*u):
    return 200, {"ok": True, "result": list(u)}


def numbered(n, update):
    return {**update, "update_id": n}


@pytest.fixture
def b(tmp_path, http):
    return botmod.Bot(store.connect(tmp_path / "t.sqlite"), TOKEN, admin_ids=[], log=lambda m: None)


def test_poll_once_handles_the_batch_and_saves_the_next_offset(b, http):
    http.script = [updates(numbered(5, msg("/start")), numbered(6, msg("hi", chat=222)))]
    assert b.poll_once() == 2
    assert json.loads(http.calls[0].body) == {"timeout": 25}
    assert subs.get_state(b.conn, botmod.OFFSET_KEY) == "7"
    http.script = [updates()]
    b.poll_once()
    assert json.loads(http.calls[-1].body) == {"timeout": 25, "offset": 7}


def test_the_offset_is_saved_so_a_restart_does_not_replay(tmp_path, http):
    path = tmp_path / "t.sqlite"
    http.script = [updates(numbered(5, msg("/start")))]
    botmod.Bot(store.connect(path), TOKEN, admin_ids=[], log=lambda m: None).poll_once()
    again = botmod.Bot(store.connect(path), TOKEN, admin_ids=[], log=lambda m: None)
    http.script = [updates()]
    again.poll_once()
    assert json.loads(http.calls[-1].body)["offset"] == 6


def test_one_bad_update_is_logged_and_skipped(tmp_path, http, monkeypatch):
    logged = []
    b = botmod.Bot(store.connect(tmp_path / "t.sqlite"), TOKEN, admin_ids=[], log=logged.append)
    real = b.handle
    monkeypatch.setattr(b, "handle", lambda u: (_ for _ in ()).throw(KeyError("boom")) if u["update_id"] == 5 else real(u))
    http.script = [updates(numbered(5, msg("x")), numbered(6, msg("/start")))]
    assert b.poll_once() == 2
    assert subs.get_state(b.conn, botmod.OFFSET_KEY) == "7" and any("update 5" in l and "boom" in l for l in logged)


def test_a_busy_database_keeps_the_update_for_the_next_poll(tmp_path, http):
    path, logged = tmp_path / "t.sqlite", []
    conn = store.connect(path)
    conn.execute("PRAGMA busy_timeout = 0")  # fail at once instead of waiting
    b = botmod.Bot(conn, TOKEN, admin_ids=[], log=logged.append)
    other = sqlite3.connect(path)  # stands in for `dbw run` in the middle of a write
    other.execute("BEGIN IMMEDIATE")
    http.script = [updates(numbered(5, msg("/start")))]
    assert b.poll_once() == 0
    assert subs.get_state(conn, botmod.OFFSET_KEY) is None and any("database busy" in l for l in logged)
    other.rollback()
    http.script = [updates(numbered(5, msg("/start")))]  # Telegram sends it again: the offset was not moved
    assert b.poll_once() == 1 and subs.get_state(conn, botmod.OFFSET_KEY) == "6"


def test_a_database_error_that_is_not_busy_skips_the_update(tmp_path, http, monkeypatch):
    logged = []
    b = botmod.Bot(store.connect(tmp_path / "t.sqlite"), TOKEN, admin_ids=[], log=logged.append)
    monkeypatch.setattr(b, "handle", lambda u: (_ for _ in ()).throw(sqlite3.OperationalError("no such table: x")))
    http.script = [updates(numbered(5, msg("x")))]
    assert b.poll_once() == 1 and subs.get_state(b.conn, botmod.OFFSET_KEY) == "6"


def test_the_loop_waits_after_a_telegram_error_and_goes_on(b, http):
    http.script = [fail(409, "Conflict: terminated by other getUpdates request"), updates(numbered(1, msg("/start")))]
    slept, logged, polls = [], [], iter([False, False, True])
    botmod.run(b, logged.append, stop=lambda: next(polls), sleep=slept.append)
    assert slept == [botmod.ERROR_WAIT] and subs.get_state(b.conn, botmod.OFFSET_KEY) == "2"
    assert any("409" in l for l in logged)


def test_the_loop_survives_an_error_that_is_not_telegrams(b, monkeypatch):
    answers = iter([httpclient.IncompleteRead(b""), []])

    def get_updates(token, offset=None, timeout=0):
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a
    monkeypatch.setattr(botmod.telegram, "get_updates", get_updates)
    slept, logged, polls = [], [], iter([False, False, True])
    botmod.run(b, logged.append, stop=lambda: next(polls), sleep=slept.append)
    assert slept == [botmod.ERROR_WAIT] and any("IncompleteRead" in l for l in logged)


def test_only_one_bot_at_a_time(tmp_path):
    p = tmp_path / "dbw-bot.lock"
    first = botmod.acquire_lock(p)
    try:
        assert botmod.lock_held(p)
        with pytest.raises(botmod.BotError, match="already running"):
            botmod.acquire_lock(p)
    finally:
        first.close()
    assert not botmod.lock_held(p)


def test_the_log_is_stamped_and_never_holds_the_token(tmp_path):
    log = botmod.file_log(tmp_path / "bot.log", TOKEN)
    log(f"failed https://api.telegram.org/bot{TOKEN}/getUpdates")
    text = (tmp_path / "bot.log").read_text(encoding="utf-8")
    assert TOKEN not in text and text.startswith("[") and text.endswith("\n")


# --- `dbw bot run` ----------------------------------------------------------------------------------------------

@pytest.fixture
def cfg(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md"])
    config.add_telegram_admin(p, 999)
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    return p


def test_bot_run_starts_the_loop_with_the_admins_and_releases_the_lock(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    seen = {}
    monkeypatch.setattr(botmod, "run", lambda b, log, **kw: seen.update(admins=b.admins, lang=b.admin_lang))
    assert cli.main(["bot", "--config", str(cfg)]) == 0
    assert seen == {"admins": {999}, "lang": "en"}
    assert not botmod.lock_held(botmod.lock_path())


def test_bot_run_refuses_a_second_copy(cfg, monkeypatch):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    held = botmod.acquire_lock(botmod.lock_path())
    try:
        with pytest.raises(SystemExit, match="already running"):
            cli.main(["bot", "run", "--config", str(cfg)])
    finally:
        held.close()


def test_bot_run_without_a_token_is_one_line(cfg):
    with pytest.raises(SystemExit, match="no Telegram bot token"):
        cli.main(["bot", "run", "--config", str(cfg)])
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_bot_runtime.py -v`
Expected: FAIL (`AttributeError: 'Bot' object has no attribute 'poll_once'`, `invalid choice: 'bot'`).

- [ ] **Step 3: Implement the runtime in `dbw/bot.py`**

Extend the imports at the top of `dbw/bot.py`:

```python
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from dbw import i18n, registry, store, subscribers
```

Constants (next to the others):

```python
OFFSET_KEY = "telegram_offset"  # bot_state key: the first update not yet handled
ERROR_WAIT = 5  # seconds the loop waits after Telegram fails (network down, another getUpdates running)
```

Add to `class Bot`:

```python
    # --- the loop -----------------------------------------------------------------------------------------------

    def poll_once(self):
        """Long-poll Telegram once and answer each update. The offset is saved after each update, so a restart
        never answers one twice. A busy database stops the batch: that update comes back next poll. -> updates done."""
        offset = subscribers.get_state(self.conn, OFFSET_KEY)
        batch = telegram.get_updates(self.token, offset=int(offset) if offset else None, timeout=telegram.LONG_POLL)
        done = 0
        for u in batch:
            try:
                self.handle(u)
            except sqlite3.OperationalError as e:
                if "locked" in str(e) or "busy" in str(e):  # `dbw run` is writing: try this update again next poll
                    self.log(f"database busy, will retry update {u.get('update_id')}: {e}")
                    return done
                self.log(f"update {u.get('update_id')}: failed: {e}")
            except Exception as e:  # one bad update must never stop the bot
                self.log(f"update {u.get('update_id')}: failed: {telegram.redact(e, self.token)}")
            subscribers.set_state(self.conn, OFFSET_KEY, u["update_id"] + 1)
            done += 1
        return done
```

Module-level functions after the class:

```python
def run(bot, log, stop=lambda: False, sleep=time.sleep):
    """Poll until `stop()` is true (never, for the real bot: it ends with the process). No error ends the loop:
    under cron @reboot nothing would restart it before the next reboot."""
    log("dbw bot start")
    while not stop():
        try:
            bot.poll_once()
        except telegram.TelegramError as e:
            log(f"telegram: {e}")
            sleep(ERROR_WAIT)
        except Exception as e:  # e.g. http.client.IncompleteRead, or the database locked while saving the offset
            log(f"error: {telegram.redact(e, bot.token)}")
            sleep(ERROR_WAIT)


def lock_path():
    return store.default_path().parent / "dbw-bot.lock"


def _lock(f):
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)


class _Lock:
    """An open, locked file. close() unlocks first: Windows frees a lock left on a closed file only 'at an
    unspecified time', which would make `lock_held` right after close() flaky."""

    def __init__(self, f):
        self.f = f

    def close(self):
        if self.f.closed:
            return
        if os.name == "nt":
            import msvcrt
            self.f.seek(0)
            try:
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        self.f.close()


def acquire_lock(path):
    """Hold `path` locked until the returned lock is closed. The OS drops the lock when the process ends, so a crash
    never leaves a stale lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    try:
        _lock(f)
    except OSError:
        f.close()
        raise BotError(f"another dbw bot is already running (lock {path}); stop it first, or see `dbw bot status`") from None
    return _Lock(f)


def lock_held(path):
    """True when a running bot holds the lock."""
    if not Path(path).exists():
        return False
    try:
        acquire_lock(path).close()
    except BotError:
        return True
    return False


def file_log(path, token):
    """A log function: one stamped, redacted line per call, appended to `path` (utf-8)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def log(line):
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().astimezone().isoformat(sep=' ', timespec='seconds')}] {telegram.redact(line, token)}\n")
    return log


def print_log(token):
    return lambda line: print(telegram.redact(line, token), flush=True)
```

- [ ] **Step 4: Add `dbw bot` to `dbw/cli.py`**

Add `bot` and `subscribers` to the `from dbw import ...` line (keep alphabetical order: `assess, bot, climatology, config, i18n, pctl_export, registry, report, schedule, store, subscribers`), update the module docstring's command list to include `bot, subscribers`, and add before `cmd_doctor`:

```python
def _bot_run(args):
    cfg = _load_config(args)
    if cfg is None:
        raise SystemExit(f"no {args.config}: run `dbw setup` first")
    admins = config.telegram_admin_ids(cfg)
    if not admins:
        print("note: channels.telegram.admin_ids is not set, so nobody can use /add, /remove or /list "
              "(run `dbw telegram admin-id --write`)", flush=True)
    try:
        token = _telegram_token(args.config)
    except telegram.TelegramError as e:
        raise SystemExit(str(e))
    try:
        lock = bot.acquire_lock(bot.lock_path())
    except bot.BotError as e:
        raise SystemExit(str(e))
    log = bot.file_log(args.log, token) if args.log else bot.print_log(token)
    try:
        conn = store.connect()
        conn.execute("PRAGMA busy_timeout = 30000")  # wait out the daily run's writes rather than fail at once
        bot.run(bot.Bot(conn, token, admins, config.report_language(cfg), log=log), log)
    except KeyboardInterrupt:
        log("dbw bot stop")
    finally:
        lock.close()
    return 0


def cmd_bot(args):
    return _bot_run(args)
```

In `main`, after the `send-test` parser:

```python
    bt = sub.add_parser("bot", help="the Telegram sign-up bot: run it here, or install it to start at login")
    bt.add_argument("action", nargs="?", default="run", choices=("run",))
    bt.add_argument("--log", help="append the bot's lines to this file (the installed bot uses data/dbw-bot.log)")
    bt.add_argument("--config", default=str(config.DEFAULT_PATH), help="config.yaml (default ./config.yaml)")
    bt.set_defaults(func=cmd_bot)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bot_runtime.py tests/test_bot.py tests/test_cli.py -v`
Expected: PASS. Then the whole suite, since `dbw/cli.py` now imports more modules: `.venv/bin/python -m pytest -q`
Expected: all pass (on Windows without symlinks, only the known `test_codex_link...` failure).

- [ ] **Step 6: Commit**

```bash
git add dbw/bot.py dbw/cli.py tests/test_bot_runtime.py
git commit -m "bot: long-poll loop, saved offset, single-instance lock, dbw bot run"
```

---

### Task 8: Start the bot at login — `dbw bot install | uninstall | status`

**Files:**
- Create: `dbw/bot_service.py`
- Modify: `dbw/cli.py` (`cmd_bot` and the `bot` parser)
- Test: `tests/test_bot_service.py`

**Interfaces:**
- Consumes: from `dbw/schedule.py`: `check_runner`, `default_runner`, `ScheduleError`, `_call`, `_why`, `_domain`, `_crontab`, `_task_user`, `_TASK_NS`, `RUNNERS`; Task 7 `bot.lock_held`, `bot.lock_path`.
- Produces: `LABEL = "com.desalbloomwatch.bot"`, `TASK_NAME = "DesalBloomWatchBot"`, `CRON_BEGIN`, `CRON_END`; `BotJob(root, exe, args, log)`; `make_job(root, platform=None) -> BotJob`; `plist_bytes(job)`, `cron_line(job)`, `edit_crontab(text, job_or_None)`, `schtasks_xml(job, user=None)`; `install(runner, job, run=None, home=None, uid=None, tmp=None, dry_run=False) -> list[str]`; `uninstall(runner, run=None, home=None, uid=None) -> list[str]`; `installed(runner, run=None, home=None, uid=None) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_service.py`:

```python
"""dbw/bot_service.py: start the bot at login on launchd, cron or Task Scheduler. Every system call is a fake."""
import plistlib
import sys
from pathlib import Path

import pytest

from dbw import bot as botmod, bot_service as svc, cli, schedule
from test_schedule import FakeRun

ROOT = Path("/opt/dbw")


def test_the_job_runs_the_venv_dbw_on_mac_and_linux():
    job = svc.make_job(ROOT, "darwin")
    assert job.exe == ROOT / ".venv" / "bin" / "dbw"
    assert job.args == ["bot", "run", "--log", str(ROOT / "data" / "dbw-bot.log")]


def test_on_windows_it_runs_pythonw_so_no_console_window_stays_open():
    job = svc.make_job(ROOT, "win32")
    assert job.exe == ROOT / ".venv" / "Scripts" / "pythonw.exe"
    assert job.args[:4] == ["-m", "dbw.cli", "bot", "run"]


def test_the_launchd_agent_starts_at_login_and_is_kept_alive():
    p = plistlib.loads(svc.plist_bytes(svc.make_job(ROOT, "darwin")))
    assert p["Label"] == svc.LABEL and p["RunAtLoad"] is True and p["KeepAlive"] is True
    assert p["ProgramArguments"] == [str(ROOT / ".venv/bin/dbw"), "bot", "run", "--log", str(ROOT / "data/dbw-bot.log")]
    assert p["WorkingDirectory"] == str(ROOT) and p["EnvironmentVariables"] == {"PYTHONUTF8": "1"}


@pytest.mark.skipif(sys.platform == "win32", reason="cron is not on Windows; the POSIX test paths render with backslashes")
def test_the_cron_block_is_an_at_reboot_line_and_leaves_the_daily_block_alone():
    daily = schedule.edit_crontab("MAILTO=x\n", schedule.make_job(ROOT, "07:00", "linux"))
    text = svc.edit_crontab(daily, svc.make_job(ROOT, "linux"))
    assert schedule.CRON_BEGIN in text and svc.CRON_BEGIN in text and text.startswith("MAILTO=x\n")
    (line,) = [l for l in text.splitlines() if l.startswith("@reboot")]
    assert line.startswith("@reboot cd ") and " bot run --log " in line and line.rstrip().endswith("dbw-bot.log")
    assert svc.edit_crontab(text, None) == daily


def test_the_task_xml_starts_at_logon_never_times_out_and_restarts_on_failure():
    xml = svc.schtasks_xml(svc.make_job(ROOT, "win32"), "PC\\user")
    for part in ("<LogonTrigger>", "<UserId>PC\\user</UserId>", "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>",
                 "<RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>",
                 "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", "pythonw.exe</Command>",
                 '<Arguments>-m dbw.cli bot run --log "'):
        assert part in xml, part


def test_install_on_launchd_writes_the_plist_and_bootstraps_it(tmp_path):
    run = FakeRun()
    lines = svc.install("launchd", svc.make_job(ROOT, "darwin"), run=run, home=tmp_path, uid=501)
    plist = tmp_path / "Library/LaunchAgents/com.desalbloomwatch.bot.plist"
    assert plist.exists() and ["launchctl", "bootstrap", "gui/501", str(plist)] in run.calls
    assert "installed" in lines[0]


def test_install_on_schtasks_imports_the_xml_then_starts_it_now(tmp_path):
    run = FakeRun()
    svc.install("schtasks", svc.make_job(ROOT, "win32"), run=run, tmp=tmp_path)
    assert run.calls[0][:4] == ["schtasks", "/Create", "/TN", svc.TASK_NAME]
    assert run.calls[1] == ["schtasks", "/Run", "/TN", svc.TASK_NAME]
    assert (tmp_path / "dbw-bot-task.xml").read_bytes().startswith(b"\xff\xfe")


def test_install_on_cron_adds_the_block_and_says_how_to_start_now():
    run = FakeRun({("crontab", "-l"): (0, "MAILTO=x\n", "")})
    lines = svc.install("cron", svc.make_job(ROOT, "linux"), run=run)
    assert svc.CRON_BEGIN in run.inputs[-1] and any("nohup" in l for l in lines)


def test_dry_run_changes_nothing(tmp_path):
    run = FakeRun()
    svc.install("launchd", svc.make_job(ROOT, "darwin"), run=run, home=tmp_path, uid=501, dry_run=True)
    assert run.calls == [] and not (tmp_path / "Library").exists()


def test_uninstall_and_installed_on_each_runner(tmp_path):
    run = FakeRun()
    job = svc.make_job(ROOT, "darwin")
    svc.install("launchd", job, run=run, home=tmp_path, uid=501)
    assert svc.installed("launchd", run=run, home=tmp_path, uid=501)
    assert svc.uninstall("launchd", run=run, home=tmp_path, uid=501) == ["removed: launchd bot agent"]
    assert not svc.installed("launchd", run=run, home=tmp_path, uid=501)
    gone = FakeRun({("schtasks", "/Query"): (1, "", "ERROR: The system cannot find the file specified.")})
    assert not svc.installed("schtasks", run=gone)
    assert svc.uninstall("schtasks", run=FakeRun({("schtasks", "/Delete"): (1, "", "ERROR: cannot find")})) == \
        ["not installed: nothing to remove"]


def test_cli_status_says_installed_and_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(svc, "installed", lambda runner, **kw: True)
    monkeypatch.setattr(botmod, "lock_held", lambda path: False)
    monkeypatch.setattr(cli, "_root", lambda: tmp_path)
    assert cli.main(["bot", "status", "--runner", "cron", "--config", str(tmp_path / "none.yaml")]) == 0
    out = capsys.readouterr().out
    assert "installed: yes" in out and "running: no" in out and "dbw-bot.log" in out


def test_cli_install_refuses_a_missing_config(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_root", lambda: tmp_path)
    with pytest.raises(SystemExit, match="dbw setup"):
        cli.main(["bot", "install", "--runner", "cron", "--config", str(tmp_path / "none.yaml")])


def test_cli_install_dry_run_prints_the_job(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_root", lambda: tmp_path)
    monkeypatch.setattr(schedule, "_call", FakeRun())
    assert cli.main(["bot", "install", "--runner", "cron", "--dry-run", "--config", str(tmp_path / "none.yaml")]) == 0
    out = capsys.readouterr().out
    assert "@reboot" in out and "--config" in out and "none.yaml" in out
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_bot_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'bot_service'`.

- [ ] **Step 3: Implement `dbw/bot_service.py`**

```python
"""Start `dbw bot` at login and keep it running: a launchd agent (macOS), a cron @reboot line (Linux) or a Task
Scheduler task with a logon trigger (Windows). Shaped like dbw/schedule.py: pure builders, and every system call
goes through a `run` callable so tests never touch the real service manager. The bot answers only while this
computer is on."""
import plistlib
import shlex
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from dbw import schedule

LABEL = "com.desalbloomwatch.bot"
TASK_NAME = "DesalBloomWatchBot"
CRON_BEGIN = "# BEGIN desal-bloom-watch-bot (managed by `dbw bot`; do not edit)"
CRON_END = "# END desal-bloom-watch-bot"


@dataclass(frozen=True)
class BotJob:
    root: Path
    exe: Path
    log: Path
    args: list = field(default_factory=list)


def make_job(root, platform=None):
    """The venv's `dbw bot run --log data/dbw-bot.log`; on Windows `pythonw.exe -m dbw.cli ...`, which opens no
    console window (an always-on dbw.exe would keep one open all day)."""
    root, platform = Path(root), platform or sys.platform
    log = root / "data" / "dbw-bot.log"
    if platform.startswith("win"):
        return BotJob(root, root / ".venv" / "Scripts" / "pythonw.exe", log, ["-m", "dbw.cli", "bot", "run", "--log", str(log)])
    return BotJob(root, root / ".venv" / "bin" / "dbw", log, ["bot", "run", "--log", str(log)])


# --- builders ---------------------------------------------------------------------------------------------------

def plist_bytes(job):
    out = job.root / "data" / "dbw-bot-launchd.log"  # only what escapes `--log`, such as an import crash
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [str(job.exe), *job.args],
        "WorkingDirectory": str(job.root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 60,  # a bot that keeps failing (no token) is restarted at most once a minute
        "StandardOutPath": str(out),
        "StandardErrorPath": str(out),
        "EnvironmentVariables": {"PYTHONUTF8": "1"},
    })


def cron_line(job):
    cmd = f"cd {shlex.quote(str(job.root))} && {shlex.quote(str(job.exe))} " + " ".join(shlex.quote(a) for a in job.args)
    return "@reboot " + cmd.replace("%", "\\%")


def edit_crontab(text, job):
    """crontab text with this bot's block replaced by one for `job`, or removed when `job` is None. Every other line,
    the daily run's block included, is kept. (dbw/schedule.py has the same editor for its own markers.)"""
    keep, inside = [], False
    for line in text.splitlines():
        if line == CRON_BEGIN:
            inside = True
        elif inside and line == CRON_END:
            inside = False
        elif not inside:
            keep.append(line)
    if job is not None:
        keep += [CRON_BEGIN, cron_line(job), CRON_END]
    return "".join(l + "\n" for l in keep)


def schtasks_xml(job, user=None):
    """Start at logon of the current user, no time limit, restart every minute after a failure. Same principal as the
    daily task: interactive token, least privilege, no stored password."""
    user_id = f"<UserId>{escape(user)}</UserId>" if user else ""
    args = " ".join(f'"{a}"' if a == str(job.log) or " " in a else a for a in job.args)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="{schedule._TASK_NS}">
  <RegistrationInfo><Description>Desal Bloom Watch sign-up bot</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled>{user_id}</LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">{user_id}<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(job.exe))}</Command>
      <Arguments>{escape(args)}</Arguments>
      <WorkingDirectory>{escape(str(job.root))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


# --- install / uninstall / installed ----------------------------------------------------------------------------

def _plist_path(home):
    return Path(home) / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def install(runner, job, run=None, home=None, uid=None, tmp=None, dry_run=False):
    """Install (or replace) the bot and start it now where the runner can. -> lines to print."""
    import os
    schedule.check_runner(runner)
    run = run or schedule._call
    if runner == "launchd":
        uid = os.getuid() if uid is None else uid
        plist = _plist_path(Path(home) if home else Path.home())
        if dry_run:
            return [f"dry run: would write {plist} and load it with launchctl bootstrap {schedule._domain(uid)}",
                    plist_bytes(job).decode("utf-8")]
        run(["launchctl", "bootout", f"{schedule._domain(uid)}/{LABEL}"])
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_bytes(plist_bytes(job))
        r = run(["launchctl", "bootstrap", schedule._domain(uid), str(plist)])
        if r.returncode != 0:
            raise schedule.ScheduleError(f"launchctl bootstrap failed: {schedule._why(r)}")
        return [f"installed: launchd agent {LABEL}; it starts now and at every login", f"plist: {plist}"]
    if runner == "cron":
        new = edit_crontab(schedule._crontab(run), job)
        if dry_run:
            return ["dry run: would set this crontab block:", *new[new.index(CRON_BEGIN):].splitlines()]
        r = run(["crontab", "-"], input=new)
        if r.returncode != 0:
            raise schedule.ScheduleError(f"crontab failed: {schedule._why(r)}")
        return ["installed: cron @reboot line; the bot starts at the next reboot",
                f"to start it now: cd {shlex.quote(str(job.root))} && nohup {shlex.quote(str(job.exe))} "
                + " ".join(shlex.quote(a) for a in job.args) + " >/dev/null 2>&1 &"]
    xml = schtasks_xml(job, schedule._task_user())
    if dry_run:
        return [f"dry run: would import this task as {TASK_NAME} and start it:", *xml.splitlines()]
    path = Path(tmp or tempfile.gettempdir()) / "dbw-bot-task.xml"
    path.write_bytes(b"\xff\xfe" + xml.encode("utf-16-le"))
    for args in (["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(path), "/F"], ["schtasks", "/Run", "/TN", TASK_NAME]):
        r = run(args)
        if r.returncode != 0:
            raise schedule.ScheduleError(f"schtasks failed: {schedule._why(r)}")
    return [f"installed: Task Scheduler task {TASK_NAME}; it starts now and at every logon"]


def uninstall(runner, run=None, home=None, uid=None):
    """Stop and remove the bot's job, and nothing else. -> lines to print."""
    import os
    schedule.check_runner(runner)
    run = run or schedule._call
    if runner == "launchd":
        uid = os.getuid() if uid is None else uid
        plist = _plist_path(Path(home) if home else Path.home())
        r = run(["launchctl", "bootout", f"{schedule._domain(uid)}/{LABEL}"])
        had = plist.exists()
        plist.unlink(missing_ok=True)
        return ["removed: launchd bot agent" if had or r.returncode == 0 else "not installed: nothing to remove"]
    if runner == "cron":
        text = schedule._crontab(run)
        if CRON_BEGIN not in text.splitlines():
            return ["not installed: nothing to remove"]
        new = edit_crontab(text, None)
        r = run(["crontab", "-r"]) if not new.strip() else run(["crontab", "-"], input=new)
        if r.returncode != 0:
            raise schedule.ScheduleError(f"crontab failed: {schedule._why(r)}")
        return ["removed: cron @reboot line (a bot started by hand keeps running until you stop it)"]
    run(["schtasks", "/End", "/TN", TASK_NAME])
    r = run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    if r.returncode == 0:
        return ["removed: Task Scheduler task"]
    if "cannot find" in schedule._why(r).lower():
        return ["not installed: nothing to remove"]
    raise schedule.ScheduleError(f"schtasks failed: {schedule._why(r)}")


def installed(runner, run=None, home=None, uid=None):
    import os
    schedule.check_runner(runner)
    run = run or schedule._call
    if runner == "launchd":
        uid = os.getuid() if uid is None else uid
        return _plist_path(Path(home) if home else Path.home()).exists() and \
            run(["launchctl", "print", f"{schedule._domain(uid)}/{LABEL}"]).returncode == 0
    if runner == "cron":
        return CRON_BEGIN in schedule._crontab(run).splitlines()
    return run(["schtasks", "/Query", "/TN", TASK_NAME]).returncode == 0
```

The uninstall launchd test expects `installed` to be False afterwards: the plist is gone, so `installed` is False whatever `launchctl print` answers.

- [ ] **Step 4: Wire `install | uninstall | status` into `dbw/cli.py`**

Import `bot_service` in the `from dbw import ...` line. Replace `cmd_bot` with:

```python
def cmd_bot(args):
    if args.action == "run":
        return _bot_run(args)
    cfg = _load_config(args) if Path(args.config).exists() else None
    runner = args.runner or (cfg or {}).get("runner") or schedule.default_runner()
    try:
        schedule.check_runner(runner)
        if args.action == "install":
            job = bot_service.make_job(_root())
            job = dataclasses.replace(job, args=job.args + ["--config", str(Path(args.config).resolve())])
            if not args.dry_run:
                if not Path(args.config).exists():  # the installed bot would exit and be restarted every minute
                    raise SystemExit(f"no {args.config}: run `dbw setup` first (the bot reads its admins from it)")
                if not job.exe.exists():
                    raise SystemExit(f"{job.exe} not found: make the venv first (python3 -m venv .venv && .venv/bin/pip install .)")
                job.log.parent.mkdir(parents=True, exist_ok=True)
            for line in bot_service.install(runner, job, dry_run=args.dry_run):
                print(line)
        elif args.action == "uninstall":
            for line in bot_service.uninstall(runner):
                print(line)
        else:
            log = bot_service.make_job(_root()).log
            print(f"installed: {'yes' if bot_service.installed(runner) else 'no'} ({runner})")
            print(f"running: {'yes' if bot.lock_held(bot.lock_path()) else 'no'}")
            last = log.read_text(encoding="utf-8", errors="replace").splitlines()[-1:] if log.exists() else []
            print(f"log: {log}" + (f"\nlast line: {last[0]}" if last else ""))
    except schedule.ScheduleError as e:
        raise SystemExit(str(e))
    return 0
```

and change the `bot` parser:

```python
    bt = sub.add_parser("bot", help="the Telegram sign-up bot: run it here, or install it to start at login")
    bt.add_argument("action", nargs="?", default="run", choices=("run", "install", "uninstall", "status"))
    bt.add_argument("--log", help="run: append the bot's lines to this file (the installed bot uses data/dbw-bot.log)")
    bt.add_argument("--runner", help=f"{', '.join(schedule.RUNNERS)} (default: config.yaml, else this platform's)")
    bt.add_argument("--dry-run", action="store_true", help="install: print what would be installed, change nothing")
    bt.add_argument("--config", default=str(config.DEFAULT_PATH), help="config.yaml (default ./config.yaml)")
    bt.set_defaults(func=cmd_bot)
```

The installed job runs from the repo root, so `store.default_path()` resolves to `<root>/data/dbw.sqlite` and the lock to `<root>/data/dbw-bot.lock`, the same files `dbw bot status` checks when run from the repo root.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bot_service.py tests/test_bot_runtime.py tests/test_schedule.py tests/test_schedule_cli.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dbw/bot_service.py dbw/cli.py tests/test_bot_service.py
git commit -m "bot: install, uninstall and status on launchd, cron and Task Scheduler"
```

---

### Task 9: The daily run sends every subscriber their report

**Files:**
- Create: `dbw/deliver.py`
- Modify: `dbw/schedule.py` (add `telegram_failed_for`)
- Modify: `dbw/cli.py` (`_run`: fetch subscriber plants; new `_send_subscribers`)
- Test: `tests/test_deliver.py`

**Interfaces:**
- Consumes: `subscribers.active / remove / mark_sent / wanted_plants`; `report.build_report(conn, boxes, plant_ids, day, mode=, upstream=)`; `report.write_report(rep, out_dir, formats, basemap, lang=) -> (files, notes)`; `telegram.send_report(token, chat_id, text, html_path, caption)`; `TelegramError.code`; `config.telegram_admin_ids`, `config.report_language`.
- Produces: `deliver.FORMATS = ("png", "html", "txt")`; `deliver.Outcome(total, sent, failed, removed)`; `deliver.group_dir(out, day, plants, lang) -> Path`; `deliver.telegram_sender(token) -> callable(address, text, html_path)`; `deliver.deliver(conn, boxes, day, out, senders, notify, *, basemap="none", mode=assess.MODES[0], upstream=None, log=print) -> Outcome`; `schedule.telegram_failed_for(n, m) -> "telegram failed for n of m"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deliver.py`:

```python
"""The daily run and subscribers: their plants are fetched, one report per (plants, language) group, each person
gets it once a day, a failure or a 403 never stops the others. Offline: NOAA and Telegram are fakes."""
import json
from datetime import timedelta

import pytest

from dbw import cli, config, subscribers as subs
from dbw.i18n import Msg
from test_run_daily import Erddap, TODAY, env  # noqa: F401  (env is a fixture)
from test_telegram import TOKEN, fail, http  # noqa: F401  (http is a fixture)

ADMIN = 999


def add(env, address, plants, lang="en", name=None):
    return subs.add(env.db(), name or f"P{address}", "telegram", address, plants, lang, "self")


def run(env, monkeypatch, *extra):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    env.use(Erddap(last=TODAY))
    log = env.tmp / "data" / "dbw-run.log"
    rc = cli.main(["run", "--config", env.cfg, "--log", str(log), *extra])
    return rc, log.read_text(encoding="utf-8")


def sent_to(http):
    return [json.loads(c.body)["chat_id"] for c in http.calls if c.method == "sendMessage"]


def docs_to(http):
    return [c for c in http.calls if c.method == "sendDocument"]


def test_subscriber_plants_are_fetched_too(env, http, monkeypatch):
    add(env, "1", ["hadera"])  # config.yaml has ashkelon only
    run(env, monkeypatch)
    n = env.db().execute("SELECT COUNT(*) FROM obs WHERE box='hadera'").fetchone()[0]
    assert n > 0


def test_one_report_per_group_and_each_person_gets_it(env, http, monkeypatch):
    add(env, "1", ["hadera"], "he")
    add(env, "2", ["hadera"], "he")
    add(env, "3", ["ashkelon"], "en")
    rc, log = run(env, monkeypatch)
    assert rc == 0 and log.rstrip().endswith("RESULT ok")
    groups = sorted(p.name for p in (env.reports / "subscribers" / str(TODAY)).iterdir())
    assert groups == ["en-ashkelon", "he-hadera"]
    he_html = (env.reports / "subscribers" / str(TODAY) / "he-hadera" / f"dbw-report-{TODAY}.html").read_bytes()
    assert sent_to(http) == ["1", "2", "3"] and len(docs_to(http)) == 3
    assert he_html in docs_to(http)[0].body and he_html in docs_to(http)[1].body
    he_txt = (env.reports / "subscribers" / str(TODAY) / "he-hadera" / f"dbw-report-{TODAY}.txt").read_text(encoding="utf-8")
    assert json.loads(http.calls[0].body)["text"] == he_txt and "חדרה" in he_txt
    assert "subscribers: sent 3 of 3" in log
    assert (env.reports / f"dbw-report-{TODAY}.md").exists()  # the admin's own report is still written


def test_one_failure_does_not_stop_the_others_and_makes_the_run_partial(env, http, monkeypatch):
    for a in ("1", "2", "3"):
        add(env, a, ["ashkelon"])
    http.script = [fail(500, "Internal Server Error")]  # the first sendMessage; a 500 is not retried
    rc, log = run(env, monkeypatch)
    assert rc == 0 and log.rstrip().endswith("RESULT partial: telegram failed for 1 of 3")
    assert sent_to(http) == ["1", "2", "3"]
    assert [s.last_sent for s in subs.active(env.db())] == [None, str(TODAY), str(TODAY)]


def test_a_403_removes_the_subscriber_and_tells_the_admin(env, http, monkeypatch):
    config.add_telegram_admin(env.cfg, ADMIN)
    add(env, "1", ["ashkelon"], name="Dana")
    add(env, "2", ["ashkelon"])
    http.script = [fail(403, "Forbidden: bot was blocked by the user")]
    rc, log = run(env, monkeypatch)
    assert rc == 0 and log.rstrip().endswith("RESULT ok")
    assert [s.address for s in subs.active(env.db())] == ["2"]
    admin_msgs = [json.loads(c.body)["text"] for c in http.calls
                  if c.method == "sendMessage" and json.loads(c.body)["chat_id"] == str(ADMIN)]
    assert admin_msgs == [Msg("bot.admin_blocked", name="Dana").render("en")]
    assert "1 removed" in log


def test_a_second_run_the_same_day_sends_nothing_new(env, http, monkeypatch):
    add(env, "1", ["ashkelon"])
    run(env, monkeypatch)
    n = len(http.calls)
    rc, log = run(env, monkeypatch)
    assert len(http.calls) == n and "subscribers: sent 0 of 0" in log


def test_a_dated_run_never_sends_to_subscribers(env, http, monkeypatch):
    add(env, "1", ["ashkelon"])
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    monkeypatch.setattr(cli, "build_providers", lambda names=None: {})  # a dated run fetches per day; nothing to fetch
    assert cli.main(["run", "--config", env.cfg, "--date", (TODAY - timedelta(days=3)).isoformat()]) == 0
    assert http.calls == [] and subs.active(env.db())[0].last_sent is None


def test_a_plant_gone_from_the_registry_is_skipped_not_fatal(env, http, monkeypatch):
    add(env, "1", ["ashkelon", "atlantis"])
    rc, log = run(env, monkeypatch)
    assert rc == 0 and sent_to(http) == ["1"]
    assert (env.reports / "subscribers" / str(TODAY) / "en-ashkelon-atlantis").is_dir()


def test_no_token_is_a_partial_run_naming_every_subscriber(env, http, monkeypatch):
    add(env, "1", ["ashkelon"])
    add(env, "2", ["ashkelon"])
    env.use(Erddap(last=TODAY))
    log = env.tmp / "run.log"
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    text = log.read_text(encoding="utf-8")
    assert text.rstrip().endswith("RESULT partial: telegram failed for 2 of 2") and http.calls == []


def test_no_subscribers_means_no_token_needed_and_no_line(env, http, monkeypatch):
    env.use(Erddap(last=TODAY))
    log = env.tmp / "run.log"
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    assert "subscribers:" not in log.read_text(encoding="utf-8") and log.read_text(encoding="utf-8").rstrip().endswith("RESULT ok")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_deliver.py -v`
Expected: FAIL (no files under `reports/subscribers`, no sends).

- [ ] **Step 3: Implement `dbw/deliver.py`**

```python
"""The daily report for subscribers: one report per (plants, language) group, written once into
reports/subscribers/<date>/<lang>-<plants>/ and sent to everyone in the group. Called by `dbw run` after the admin's
own report. A failure for one person never stops the others; Telegram's 403 (the person blocked the bot or deleted
their account) removes the subscriber and tells the admin."""
from dataclasses import dataclass
from pathlib import Path

from dbw import assess, report, subscribers
from dbw.channels import telegram

FORMATS = ("png", "html", "txt")  # the HTML embeds the PNG map; the txt is the message text


@dataclass
class Outcome:
    total: int = 0
    sent: int = 0
    failed: int = 0
    removed: int = 0


def group_dir(out, day, plants, lang):
    return Path(out) / "subscribers" / str(day) / f"{lang}-{'-'.join(plants)}"


def caption(text):
    return text.splitlines()[0] if text.strip() else ""


def telegram_sender(token):
    """send(address, text, html_path) over Telegram; any failure comes out as a redacted TelegramError."""
    def send(address, text, html):
        try:
            telegram.send_report(token, address, text, html, caption(text))
        except telegram.TelegramError:
            raise
        except Exception as e:
            raise telegram.TelegramError(telegram.redact(e, token)) from None
    return send


def deliver(conn, boxes, day, out, senders, notify, *, basemap="none", mode=assess.MODES[0], upstream=None, log=print):
    """Send today's report to every active subscriber who has not had it yet. `senders` maps a channel to
    send(address, text, html_path); `notify(code, **params)` tells the admins. -> Outcome."""
    due = [s for s in subscribers.active(conn) if s.last_sent != day.isoformat()]
    known = {b.id for b in boxes if b.kind == "plant"}
    groups = {}
    for s in due:
        groups.setdefault((tuple(sorted(s.plants)), s.language), []).append(s)
    done = Outcome(total=len(due))
    for (plants, lang), members in groups.items():
        usable = [p for p in plants if p in known]  # a plant dropped from plants.yaml is skipped, not fatal
        try:
            if not usable:
                raise ValueError(f"none of {', '.join(plants)} is in plants.yaml")
            rep = report.build_report(conn, boxes, usable, day, mode=mode, upstream=upstream)
            files, _ = report.write_report(rep, group_dir(out, day, plants, lang), FORMATS, basemap, lang=lang)
            text = files["txt"].read_text(encoding="utf-8")
        except Exception as e:
            log(f"subscribers {lang} {','.join(plants)}: report failed: {e}")
            done.failed += len(members)
            continue
        for s in members:
            try:
                send = senders.get(s.channel)
                if send is None:
                    raise RuntimeError(f"no sender for channel {s.channel}")
                send(s.address, text, files["html"])
                subscribers.mark_sent(conn, s.id, day)
            except telegram.TelegramError as e:
                if e.code == 403:
                    subscribers.remove(conn, s.id)
                    log(f"subscriber {s.id} {s.name}: removed (Telegram 403: blocked the bot or deleted the account)")
                    notify("bot.admin_blocked", name=s.name)
                    done.removed += 1
                else:
                    log(f"subscriber {s.id} {s.name}: failed: {e}")
                    done.failed += 1
            except Exception as e:
                log(f"subscriber {s.id} {s.name}: failed: {e}")
                done.failed += 1
            else:
                log(f"subscriber {s.id} {s.name}: sent")
                done.sent += 1
    return done
```

- [ ] **Step 4: Add the partial reason to `dbw/schedule.py`**

After `PARTIAL = partial(UPSTREAM)`:

```python
def telegram_failed_for(n, m):
    """The reason when n of the m subscribers due today did not get their report."""
    return f"{TELEGRAM} for {n} of {m}"
```

- [ ] **Step 5: Wire it into `dbw run` (`dbw/cli.py`)**

Add `deliver` to the `from dbw import ...` line and `from dbw.i18n import Msg` to the imports.

In `_run`, replace

```python
    plants = _csv(args.plants) or (cfg or {}).get("plants")
    boxes = select_boxes(registry.load(), plants)
    t0 = time.monotonic()
    conn = store.connect()
```

with

```python
    conn = store.connect()
    all_boxes = registry.load()
    plants = _csv(args.plants) or (cfg or {}).get("plants")
    if plants and not args.plants and not args.date:  # the daily run also fetches the plants subscribers chose
        known = {b.id for b in all_boxes if b.kind == "plant"}
        plants = list(dict.fromkeys([*plants, *(p for p in subscribers.wanted_plants(conn) if p in known)]))
    boxes = select_boxes(all_boxes, plants)
    t0 = time.monotonic()
```

and at the end of `_run` replace

```python
    if sending and not _send_telegram(cfg, args.config, files):
        reasons.append(schedule.TELEGRAM)
    return schedule.partial(*reasons) if reasons else schedule.OK
```

with

```python
    if sending and not _send_telegram(cfg, args.config, files):
        reasons.append(schedule.TELEGRAM)
    if not args.date:  # a dated re-run never sends to subscribers
        reasons += _send_subscribers(conn, cfg, args.config, day, out, basemap, args.mode, upstream)
    return schedule.partial(*reasons) if reasons else schedule.OK
```

Add after `_send_telegram`:

```python
def _send_subscribers(conn, cfg, config_path, day, out, basemap, mode, upstream):
    """Today's report to every subscriber who has not had it yet (dbw/deliver.py). -> [partial reason] or []."""
    if not subscribers.active(conn):
        return []
    due = [s for s in subscribers.active(conn) if s.last_sent != day.isoformat()]
    try:
        token = _telegram_token(config_path)
    except telegram.TelegramError as e:
        print(f"subscribers: failed: {e}")
        return [schedule.telegram_failed_for(len(due), len(due))] if due else []
    lang = config.report_language(cfg)

    def notify(code, **params):
        for admin in config.telegram_admin_ids(cfg):
            try:
                telegram.send_message(token, admin, Msg(code, **params).render(lang))
            except Exception as e:
                print(f"telegram: admin {admin} not told: {telegram.redact(e, token)}")

    done = deliver.deliver(conn, registry.load(), day, out, {"telegram": deliver.telegram_sender(token)}, notify,
                           basemap=basemap, mode=mode, upstream=upstream)
    print(f"subscribers: sent {done.sent} of {done.total}" + (f", {done.removed} removed" if done.removed else "")
          + (f", {done.failed} failed" if done.failed else ""))
    return [schedule.telegram_failed_for(done.failed, done.total)] if done.failed else []
```

`no_subscribers_means_no_token_needed_and_no_line` holds because the function returns before touching the token when nobody is subscribed.

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_deliver.py tests/test_run_daily.py tests/test_telegram_cli.py tests/test_schedule.py -v`
Expected: PASS. Then the whole suite, since `_run` changed: `.venv/bin/python -m pytest -q`
Expected: all pass (on Windows without symlinks, only the known `test_codex_link...` failure).

- [ ] **Step 7: Commit**

```bash
git add dbw/deliver.py dbw/schedule.py dbw/cli.py tests/test_deliver.py
git commit -m "run: send each subscriber the report for their plants and language"
```

---

### Task 10: On the computer — `dbw subscribers` and `dbw telegram admin-id`

**Files:**
- Modify: `dbw/cli.py` (`cmd_subscribers`, `_known_chats`, `_chat_id_step`, `cmd_telegram`, parsers)
- Test: `tests/test_subscribers_cli.py` (append)

**Interfaces:**
- Consumes: `subscribers.*`, `config.prompt_plants(boxes, input_fn, say)`, `config.prompt_language(input_fn, say)`, `config.add_telegram_admin`, `telegram.get_updates / chats_from_updates / describe_chat`.
- Produces: `dbw subscribers list | add | remove <id> | export [--out FILE]`; `dbw telegram admin-id [--write] [--pick ID]`; `dbw telegram chat-id` now also lists contacts the bot recorded.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_subscribers_cli.py`:

```python
import json

from dbw import cli, store, subscribers as subs
from test_telegram import TOKEN, Http, fail, http  # noqa: F401  (http is a fixture)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    return store.connect(tmp_path / "t.sqlite")


@pytest.fixture
def cfgp(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md"])
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    return p


def answers(monkeypatch, *replies):
    it = iter(replies)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))


def test_list_empty_then_one_line_per_subscriber(db, capsys):
    assert cli.main(["subscribers", "list"]) == 0
    assert "no subscribers yet" in capsys.readouterr().out
    subs.add(db, "Dana", "telegram", "111", ["hadera"], "he", "self")
    cli.main(["subscribers", "list"])
    out = capsys.readouterr().out
    assert "Dana" in out and "telegram 111" in out and "hadera" in out and "he" in out


def test_add_picks_a_contact_then_asks_name_plants_language(db, monkeypatch, capsys):
    subs.touch_contact(db, "telegram", "111", "Dana", "private", 100)
    subs.touch_contact(db, "telegram", "-100222", "Plant ops", "supergroup", 200)
    answers(monkeypatch, "2", "", "hadera,eilat", "he")  # 2 = Dana (newest first: Plant ops is 1); Enter keeps her name
    assert cli.main(["subscribers", "add"]) == 0
    (s,) = subs.active(db)
    assert (s.address, s.name, s.plants, s.language, s.added_by) == ("111", "Dana", ("hadera", "eilat"), "he", "admin")


def test_add_with_nobody_known_says_how_to_get_someone(db):
    with pytest.raises(SystemExit, match="message the bot"):
        cli.main(["subscribers", "add"])


def test_remove_by_id(db, capsys):
    s = subs.add(db, "Dana", "telegram", "111", ["hadera"], "he", "self")
    assert cli.main(["subscribers", "remove", str(s.id)]) == 0
    assert subs.active(db) == [] and "removed" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="no active subscriber"):
        cli.main(["subscribers", "remove", str(s.id)])


def test_export_writes_every_row_as_json(db, tmp_path):
    subs.add(db, "Dana", "telegram", "111", ["hadera"], "he", "self")
    out = tmp_path / "backup.json"
    assert cli.main(["subscribers", "export", "--out", str(out)]) == 0
    assert [r["name"] for r in json.loads(out.read_text(encoding="utf-8"))] == ["Dana"]


def test_admin_id_writes_a_private_chat_only(db, cfgp, http):
    subs.touch_contact(db, "telegram", "-100222", "Plant ops", "supergroup", 200)
    subs.touch_contact(db, "telegram", "111", "Dana", "private", 100)
    http.script = [(200, {"ok": True, "result": []})]
    assert cli.main(["telegram", "admin-id", "--write", "--config", str(cfgp)]) == 0
    assert config.telegram_admin_ids(config.load(cfgp)) == [111]


def test_chat_id_also_lists_contacts_the_bot_recorded(db, cfgp, http, capsys):
    subs.touch_contact(db, "telegram", "111", "Dana", "private", 1790000000)
    http.script = [fail(409, "Conflict: terminated by other getUpdates request")]  # the bot is polling
    assert cli.main(["telegram", "chat-id", "--config", str(cfgp)]) == 0
    assert "111  private  Dana" in capsys.readouterr().out
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_subscribers_cli.py -v`
Expected: FAIL (`invalid choice: 'subscribers'`, `invalid choice: 'admin-id'`).

- [ ] **Step 3: Implement in `dbw/cli.py`**

Replace `_chat_id_step` and `cmd_telegram` with:

```python
def _known_chats(path):
    """Chats that have messaged the bot: Telegram's pending updates plus the contacts `dbw bot` recorded (once the
    bot runs, it takes the updates first, and a second reader may get 'Conflict')."""
    found = {int(c["address"]): {"id": int(c["address"]), "type": c["type"], "name": c["name"], "last": c["last"]}
             for c in subscribers.contacts(store.connect())}
    try:
        updates = telegram.get_updates(_telegram_token(path))
    except telegram.TelegramError:
        if not found:
            raise
        updates = []
    for c in telegram.chats_from_updates(updates):
        found[c["id"]] = c
    return sorted(found.values(), key=lambda c: -c["last"])


def _chat_id_step(config_path, write, pick, admin=False):
    """List the chats that have messaged the bot; with `write`, add the chosen one to the config (as a report chat,
    or with `admin` as an admin: private chats only). -> exit code."""
    path = Path(config_path)
    if pick is not None and not write:
        raise SystemExit("--pick works with --write only")
    if write and not path.exists():
        raise SystemExit(f"no {path}: run `dbw setup` first")
    try:
        chats = _known_chats(path)
    except telegram.TelegramError as e:
        raise SystemExit(str(e))
    if admin:
        chats = [c for c in chats if c["type"] == "private"]
    if not chats:
        print("No chat has messaged the bot yet: send your bot a message first (open it in Telegram and press Start; "
              "for a group, add the bot and write something there), then run this again. Telegram keeps unread "
              "messages for 24 hours.")
        return 1
    for chat in chats:
        print(f"  {telegram.describe_chat(chat)}")
    action = "admin-id" if admin else "chat-id"
    if not write:
        print(f"To save one: dbw telegram {action} --write   (add --pick <id> when there are several)")
        return 0
    if pick is None:
        if len(chats) > 1:
            raise SystemExit("several chats found: choose one with --pick <id>")
        pick = chats[0]["id"]
    elif str(pick).strip() not in {str(c["id"]) for c in chats}:
        raise SystemExit(f"{pick} is not one of the chats listed above")
    try:
        (config.add_telegram_admin if admin else config.add_telegram_chat)(path, pick)
    except (config.ConfigError, ValueError) as e:
        raise SystemExit(str(e))
    if admin:
        print(f"added {pick} to {path} as admin. Restart the bot to use it (`dbw bot install` again, or stop and "
              f"start `dbw bot run`).")
    else:
        print(f"added {pick} to {path}: telegram is on. Check it with `dbw send-test telegram`.")
    return 0


def cmd_telegram(args):
    return _chat_id_step(args.config, args.write, args.pick, admin=args.action == "admin-id")
```

Check the existing `test_telegram_cli.py` expectations on the "single chat" path: with one private chat found, `admin-id --write` writes it without `--pick`, exactly like `chat-id`. In `test_admin_id_writes_a_private_chat_only` only one private chat remains after filtering, so no `--pick` is needed.

Add before `cmd_doctor`:

```python
def _describe_sub(s):
    return (f"  {s.id:>3}  {s.name}  {s.channel} {s.address}  {','.join(s.plants)}  {s.language}  "
            f"added by {s.added_by} {s.created_at[:10]}" + (f"  last sent {s.last_sent}" if s.last_sent else ""))


def _subscribers_add(conn):
    taken = {s.address for s in subscribers.active(conn)}
    people = [c for c in subscribers.contacts(conn) if c["address"] not in taken]
    if not people:
        raise SystemExit("nobody to add: ask them to message the bot first (with `dbw bot` running), then run this again")
    for i, c in enumerate(people, 1):
        print(f"  {i:2d}. {c['name']}  ({c['type']} {c['address']})")
    while True:
        pick = input("Who (number): ").strip()
        if pick.isdigit() and 0 < int(pick) <= len(people):
            break
        print(f"  not understood: {pick}")
    person = people[int(pick) - 1]
    while True:
        try:
            name = subscribers.clean_name(input(f"Name [{person['name']}]: ").strip() or person["name"])
            break
        except ValueError as e:
            print(f"  {e}")
    plants = config.prompt_plants(registry.load(), input_fn=input)  # the default is bound at import: pass it
    lang = config.prompt_language(input_fn=input)
    s = subscribers.add(conn, name, "telegram", person["address"], plants, lang, "admin")
    print(f"added: {_describe_sub(s).strip()}")


def cmd_subscribers(args):
    conn = store.connect()
    if args.action == "list":
        rows = subscribers.active(conn)
        for s in rows:
            print(_describe_sub(s))
        if not rows:
            print("no subscribers yet: people sign up by messaging the bot (`dbw bot`), or use `dbw subscribers add`")
        return 0
    if args.action == "add":
        _subscribers_add(conn)
        return 0
    if args.action == "remove":
        if not (args.id or "").isdigit():
            raise SystemExit("remove needs the subscriber id: see `dbw subscribers list`")
        s = subscribers.remove(conn, int(args.id))
        if s is None:
            raise SystemExit(f"no active subscriber {args.id}: see `dbw subscribers list`")
        print(f"removed: {s.id} {s.name} (they are not told; the Telegram /remove tells them)")
        return 0
    out = Path(args.out or store.default_path().parent / f"subscribers-{date.today()}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = subscribers.export(conn)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"exported {len(rows)} rows to {out}")
    return 0
```

Parsers in `main`: change the telegram parser's action and help, and add `subscribers`:

```python
    tg = sub.add_parser("telegram", help="set up the Telegram channel: find the chat id of people who messaged the bot")
    tg.add_argument("action", choices=("chat-id", "admin-id"),
                    help="chat-id: the chats that get the admin report; admin-id: who may use /add, /remove, /list")
    ...
    sb = sub.add_parser("subscribers", help="the people who get the daily report: list, add, remove, export")
    sb.add_argument("action", choices=("list", "add", "remove", "export"))
    sb.add_argument("id", nargs="?", help="remove: the subscriber id (see `dbw subscribers list`)")
    sb.add_argument("--out", help="export: the file to write (default data/subscribers-<date>.json)")
    sb.set_defaults(func=cmd_subscribers)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_subscribers_cli.py tests/test_telegram_cli.py -v`
Expected: PASS. Then the whole suite: `.venv/bin/python -m pytest -q`
Expected: all pass (on Windows without symlinks, only the known `test_codex_link...` failure).

- [ ] **Step 5: Commit**

```bash
git add dbw/cli.py tests/test_subscribers_cli.py
git commit -m "cli: dbw subscribers list/add/remove/export, dbw telegram admin-id"
```

---

### Task 11: `dbw doctor` checks, docs, full suite, PR

**Files:**
- Modify: `dbw/cli.py` (`cmd_doctor`, doctor parser)
- Modify: `tests/test_cli.py` (pass `--config` in the two doctor tests; add new ones)
- Modify: `docs/telegram.md`, `config.example.yaml`, `README.md`

**Interfaces:**
- Consumes: `config.telegram_admin_ids`, `subscribers.active`, `bot.lock_held`, `bot.lock_path`.
- Produces: `dbw doctor [--config FILE]` with two lines once subscriptions are in use: `telegram admin_ids: ...` and `bot: ...`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_cli.py`, change both `cli.main(["doctor"])` calls to `cli.main(["doctor", "--config", str(tmp_path / "none.yaml")])` (so the developer's own `config.yaml` never leaks in), then append:

```python
def _doctor_env(tmp_path, monkeypatch):
    from dbw import config, registry
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))

    class Up:
        source = "src_up"

        def fetch(self, box, day):
            return NoData("all_nan: 0/20 valid", total_count=20)
    monkeypatch.setattr(cli, "build_providers", lambda names=None: {"src_up": Up()})
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md"])
    return p


def test_doctor_is_silent_about_the_bot_when_subscriptions_are_not_used(tmp_path, monkeypatch, capsys):
    p = _doctor_env(tmp_path, monkeypatch)
    assert cli.main(["doctor", "--config", str(p)]) == 0
    out = capsys.readouterr().out
    assert "admin_ids" not in out and "bot:" not in out


def test_doctor_checks_admin_ids_and_the_bot_once_subscriptions_are_used(tmp_path, monkeypatch, capsys):
    from dbw import bot, config, store, subscribers
    p = _doctor_env(tmp_path, monkeypatch)
    subscribers.add(store.connect(), "Dana", "telegram", "111", ["hadera"], "he", "self")
    assert cli.main(["doctor", "--config", str(p)]) == 1
    out = capsys.readouterr().out
    assert "FAIL telegram admin_ids: not set" in out and "FAIL bot: not running" in out
    config.add_telegram_admin(p, 999)
    held = bot.acquire_lock(bot.lock_path())
    try:
        assert cli.main(["doctor", "--config", str(p)]) == 0
    finally:
        held.close()
    out = capsys.readouterr().out
    assert "OK   telegram admin_ids: 1 set" in out and "OK   bot: running" in out
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: FAIL (`unrecognized arguments: --config`).

- [ ] **Step 3: Implement**

In `cmd_doctor`, after the `db` check (before the provider loop), add:

```python
    try:
        cfg = config.load(args.config)
    except config.ConfigError as e:
        report(False, f"config: {e}")
        cfg = None
    admins = config.telegram_admin_ids(cfg)
    try:
        in_use = bool(admins) or bool(subscribers.active(store.connect()))
    except Exception:
        in_use = bool(admins)
    if in_use:  # checked only once subscriptions are used, so nobody else sees a new FAIL
        report(bool(admins), f"telegram admin_ids: {len(admins)} set" if admins
               else "telegram admin_ids: not set (run `dbw telegram admin-id --write`)")
        running = bot.lock_held(bot.lock_path())
        report(running, "bot: running" if running else "bot: not running (start it with `dbw bot install`)")
```

and give the doctor parser a config option:

```python
    d = sub.add_parser("doctor", help="check registry, database, source reachability and, once used, the sign-up bot")
    d.add_argument("--config", default=str(config.DEFAULT_PATH), help="config.yaml (default ./config.yaml)")
    d.set_defaults(func=cmd_doctor)
```

- [ ] **Step 4: Docs**

`config.example.yaml`, inside `channels.telegram` after `chat_ids`, add:

```yaml
    admin_ids: [123456789]  # who may use the bot's /add, /remove and /list (your own Telegram user id = your private
                            # chat id). `dbw telegram admin-id --write` fills it in. Optional; the bot runs without it.
```

`docs/telegram.md`, append a section:

```markdown
## Subscriptions: a sign-up bot

People can ask for the daily report themselves. Each one picks plants and a language (English, Hebrew or Arabic).

1. Make yourself the admin: message the bot, then `dbw telegram admin-id --write`.
2. Start the bot and keep it running: `dbw bot install` (starts now and at every login; `dbw bot status`,
   `dbw bot uninstall`). To try it in the foreground: `dbw bot run` (Ctrl+C stops it).
   It answers only while this computer is on; messages sent while it is off wait up to 24 hours at Telegram.
3. Share the bot's link (t.me/<your bot>). A person presses Start, picks a language, a name, the plants, and
   confirms. You get "New subscriber: ..." with a [Remove] button.

| Who | Sends | What happens |
|---|---|---|
| Anyone | `/start` | Sign up; a subscriber gets: change plants, change language, stop |
| Anyone | `/stop` | Stop the daily report (asks first) |
| Anyone | `/help` | Short help in their language |
| Admin | `/add` | Add a chat that has messaged the bot; in a group, "This chat" adds the group |
| Admin | `/remove` | Remove someone (they are told) |
| Admin | `/list` | Everyone, with plants and language |

On the computer: `dbw subscribers list`, `dbw subscribers add` (asks in the terminal, from the chats that messaged
the bot), `dbw subscribers remove <id>` (does not tell them), `dbw subscribers export` (a JSON backup in `data/`).

The daily run (`dbw run`) sends the reports: one report per plants-and-language group, saved under
`reports/subscribers/<date>/`. Each person gets it once a day; `dbw run --date ...` never sends to subscribers.
A person who blocks the bot is removed automatically and you are told. If some sends fail,
`dbw schedule status` shows `partial: telegram failed for N of M`. `dbw doctor` checks the bot and `admin_ids`
once subscriptions are in use.
```

`README.md`: in the Telegram part of the feature list (find the line that mentions Telegram), add one sentence: "People can also sign up themselves through the bot and choose their plants and language (docs/telegram.md, Subscriptions)."

Check: `grep -c "sign up themselves" README.md` prints `1`; `grep -c "## Subscriptions" docs/telegram.md` prints `1`; `grep -c admin_ids config.example.yaml` prints at least `1`.

- [ ] **Step 5: Full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass (on Windows without symlinks, only the known `test_codex_link_is_a_relative_symlink_to_the_skill_folder` failure).

- [ ] **Step 6: Public-repo scan, commit, push, PR**

```bash
git grep -nE "goomal@|@gmail|[0-9]{8,10}:[A-Za-z0-9_-]{30,}" -- . ':!docs/superpowers' || echo "clean"  # the public Pages URL goomal.github.io is fine
git add dbw/cli.py tests/test_cli.py docs/telegram.md config.example.yaml README.md
git commit -m "doctor: bot and admin_ids checks; docs: subscriptions"
git push -u origin subscriptions-design
gh pr create --base main --title "Subscriptions: Telegram sign-up bot" --body "<summary, the 15 plan decisions, test results>"
```

Expected: `clean`; CI green on ubuntu, macOS and Windows.

- [ ] **Step 7: Live check (the admin runs these; needs the real token in `.env`)**

```bash
dbw telegram admin-id --write
dbw bot run            # in a second terminal; message the bot from a phone: /start, sign up, /list
dbw run                # the subscriber gets the report
dbw bot install && dbw bot status
```
