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
