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
