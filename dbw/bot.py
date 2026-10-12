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
