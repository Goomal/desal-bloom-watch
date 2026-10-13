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


def update(conn, sub_id, plants=None, language=None, name=None):
    s = get(conn, sub_id)
    name = clean_name(name) if name is not None else s.name
    plants = list(plants) if plants is not None else list(s.plants)
    language = language or s.language
    _check(plants, language)
    with conn:
        conn.execute("UPDATE subscribers SET name=?, plants=?, language=? WHERE id=?",
                     (name, json.dumps(plants), language, sub_id))
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
