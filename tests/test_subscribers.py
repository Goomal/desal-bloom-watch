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
