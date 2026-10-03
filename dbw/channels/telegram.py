"""Telegram Bot API: send the short message and the HTML report to a chat, find a chat id. Standard library only.
The bot token comes from DBW_TELEGRAM_TOKEN (environment, else the .env file) and never leaves this module: every error
line is redacted before it is raised. All network access goes through `_http`, the one seam the tests replace."""
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.telegram.org"
TOKEN_VAR = "DBW_TELEGRAM_TOKEN"
MESSAGE_LIMIT = 4096  # sendMessage: characters, counted in UTF-16 units
CAPTION_LIMIT = 1024  # sendDocument caption
MAX_WAIT = 30  # seconds: the longest a retry waits, whatever `retry_after` says
NETWORK_WAIT = 2  # seconds before the one retry after a network error
DEFAULT_RETRY_AFTER = 5
TIMEOUT = 30


class TelegramError(Exception):
    """One plain line the user can act on. Never contains the token."""


def _sleep(seconds):
    time.sleep(seconds)


def _http(url, body, content_type):
    """POST `body` to `url` -> (HTTP status, response bytes). An HTTP error status is a result, not an exception;
    a network problem raises OSError."""
    req = urllib.request.Request(url, data=body, headers={"Content-Type": content_type}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# --- the token ----------------------------------------------------------------------------------------------

def parse_dotenv(text):
    """KEY=VALUE lines -> dict. Blank lines, comments and lines without a key are ignored; `export ` and one pair of
    quotes around the value are dropped."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def load_token(dotenv=None):
    """The bot token: the environment first, else `dotenv` (default ./.env). One clear line when it is missing."""
    token = (os.environ.get(TOKEN_VAR) or "").strip()
    if not token:
        path = Path(dotenv) if dotenv else Path(".env")
        if path.is_file():
            token = parse_dotenv(path.read_text(encoding="utf-8-sig")).get(TOKEN_VAR, "").strip()
    if not token:
        raise TelegramError(f"no Telegram bot token: set {TOKEN_VAR} in the environment or in the .env file next to "
                            f"config.yaml (see docs/telegram.md)")
    return token


def redact(text, token):
    """`text` with the bot token, its URL form and anything token-shaped hidden."""
    text = str(text)
    if token:
        text = text.replace(f"bot{token}", "bot<redacted>").replace(token, "<redacted>")
    text = re.sub(r"bot\d{6,}:[\w-]{20,}", "bot<redacted>", text)
    return re.sub(r"\d{8,10}:[\w-]{30,}", "<redacted>", text)


# --- one API call -------------------------------------------------------------------------------------------

def _call(token, method, body, content_type="application/json"):
    """POST one Bot API method -> its `result`. Retries once after a network error or a 429 (waiting `retry_after`,
    capped at MAX_WAIT); any other failure raises TelegramError("<method>: HTTP <code>: <description>")."""
    url = f"{API}/bot{token}/{method}"
    for attempt in (1, 2):
        try:
            code, raw = _http(url, body, content_type)
        except OSError as e:
            if attempt == 1:
                _sleep(NETWORK_WAIT)
                continue
            raise TelegramError(redact(f"{method}: network error ({getattr(e, 'reason', None) or e})", token)) from None
        except ValueError as e:  # http.client refuses the URL (a stray control character in the token) and quotes it
            raise TelegramError(redact(f"{method}: invalid request ({e})", token)) from None
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        data = data if isinstance(data, dict) else {}
        if code == 200 and data.get("ok") is True:
            return data.get("result")
        if code == 429 and attempt == 1:
            wait = (data.get("parameters") or {}).get("retry_after") or DEFAULT_RETRY_AFTER
            _sleep(min(wait, MAX_WAIT))
            continue
        description = data.get("description")
        raise TelegramError(redact(f"{method}: HTTP {code}" + (f": {description}" if description else ""), token))


# --- sending ------------------------------------------------------------------------------------------------

def _units(s):
    return len(s.encode("utf-16-le")) // 2


def _hard(text, limit):
    out, cur = [], ""
    for ch in text:
        if _units(cur) + _units(ch) > limit:
            out.append(cur)
            cur = ""
        cur += ch
    return out + [cur]


def _pack(text, limit, seps=("\n\n", "\n")):
    """`text` as chunks of at most `limit` UTF-16 units, cut at paragraph breaks, else line breaks, else anywhere."""
    if _units(text) <= limit:
        return [text]
    if not seps:
        return _hard(text, limit)
    sep, rest = seps[0], seps[1:]
    chunks, cur = [], None
    for part in text.split(sep):
        for piece in _pack(part, limit, rest):
            if cur is None:
                cur = piece
            elif _units(cur) + _units(sep) + _units(piece) <= limit:
                cur += sep + piece
            else:
                chunks.append(cur)
                cur = piece
    return chunks + [cur]


def split_text(text, limit=MESSAGE_LIMIT):
    return _pack(text, limit)


def send_message(token, chat_id, text):
    """Plain text, no parse_mode. A text over the 4,096-character limit goes as several messages, cut at paragraphs."""
    for chunk in split_text(text):
        _call(token, "sendMessage", json.dumps({"chat_id": str(chat_id), "text": chunk}).encode("utf-8"))


def _multipart(fields, file_field, path, content_type):
    boundary = "dbw" + uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode("utf-8")
    filename = path.name.replace('"', "")
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
             f"Content-Type: {content_type}\r\n\r\n").encode("utf-8") + path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def send_document(token, chat_id, path, caption=""):
    """Upload `path` (the HTML report) as a document, with a caption cut to Telegram's limit."""
    if len(caption) > CAPTION_LIMIT:
        caption = caption[:CAPTION_LIMIT - 1] + "…"
    fields = {"chat_id": str(chat_id)}
    if caption:
        fields["caption"] = caption
    body, ctype = _multipart(fields, "document", Path(path), "text/html")
    _call(token, "sendDocument", body, ctype)


def send_report(token, chat_id, text, html_path, caption):
    """The day's delivery to one chat: the short message, then the HTML file (when there is one)."""
    send_message(token, chat_id, text)
    if html_path:
        send_document(token, chat_id, html_path, caption)


# --- finding a chat id --------------------------------------------------------------------------------------

def get_updates(token):
    """The pending updates for the bot (what people sent it since it last fetched them; Telegram keeps them 24 h)."""
    return _call(token, "getUpdates", json.dumps({"timeout": 0}).encode("utf-8")) or []


def chats_from_updates(updates):
    """[{id, type, name, last}] for every chat that appears in `updates`, newest message first."""
    found = {}
    for update in updates:
        for value in update.values():
            chat = value.get("chat") if isinstance(value, dict) else None
            if not isinstance(chat, dict) or "id" not in chat:
                continue
            name = (chat.get("title") or " ".join(p for p in (chat.get("first_name"), chat.get("last_name")) if p)
                    or (f"@{chat['username']}" if chat.get("username") else ""))
            entry = found.setdefault(chat["id"], {"id": chat["id"], "type": chat.get("type", ""), "name": name, "last": 0})
            entry["last"] = max(entry["last"], value.get("date") or 0)
    return sorted(found.values(), key=lambda c: -c["last"])


def describe_chat(chat):
    line = "  ".join(str(p) for p in (chat["id"], chat["type"], chat["name"]) if p)
    if chat["last"]:
        when = datetime.fromtimestamp(chat["last"], timezone.utc)
        line += f"  last message {when:%Y-%m-%d %H:%M} UTC"
    return line
