"""dbw/channels/telegram.py: the Bot API calls over a fake HTTP layer. Offline; the fake token is built at run time."""
import json
import urllib.error
from types import SimpleNamespace

import pytest

from dbw.channels import telegram

TOKEN = "123456789" + ":" + "AAH" * 12  # fake, built so no token-shaped literal sits in the source


class Http:
    """Stands in for telegram._http(url, body, content_type) -> (code, bytes). `script` is a list of (code, payload)
    or exceptions to raise; once it runs out every call answers 200 ok."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, url, body, content_type):
        self.calls.append(SimpleNamespace(url=url, body=body, ctype=content_type, method=url.rsplit("/", 1)[1]))
        r = self.script.pop(0) if self.script else (200, {"ok": True, "result": {}})
        if isinstance(r, BaseException):
            raise r
        code, payload = r
        return code, json.dumps(payload).encode()


@pytest.fixture
def http(monkeypatch):
    h = Http()
    monkeypatch.setattr(telegram, "_http", h)
    return h


@pytest.fixture
def sleeps(monkeypatch):
    got = []
    monkeypatch.setattr(telegram, "_sleep", got.append)
    return got


def fail(code, description, **parameters):
    return code, {"ok": False, "error_code": code, "description": description, "parameters": parameters}


# --- sendMessage --------------------------------------------------------------------------------------------

def test_send_message_posts_plain_text_json_with_no_parse_mode(http):
    telegram.send_message(TOKEN, "42", "hello <b>there</b> & more")
    (c,) = http.calls
    assert c.url == f"https://api.telegram.org/bot{TOKEN}/sendMessage" and c.ctype == "application/json"
    assert json.loads(c.body) == {"chat_id": "42", "text": "hello <b>there</b> & more"}


def test_send_message_splits_a_long_text_on_paragraph_boundaries(http):
    paras = [f"paragraph {i}: " + "x" * 700 for i in range(12)]
    telegram.send_message(TOKEN, "42", "\n\n".join(paras))
    sent = [json.loads(c.body)["text"] for c in http.calls]
    assert len(sent) == 3 and all(len(t) <= 4096 for t in sent)
    assert "\n\n".join(sent) == "\n\n".join(paras)  # lossless, in order, no paragraph cut in two


def test_send_message_splits_one_oversized_paragraph_without_losing_a_character(http):
    text = "".join(f"{i % 10}" for i in range(9000))
    telegram.send_message(TOKEN, "42", text)
    sent = [json.loads(c.body)["text"] for c in http.calls]
    assert len(sent) == 3 and all(len(t) <= 4096 for t in sent) and "".join(sent) == text


def test_split_text_counts_utf16_units_like_telegram():
    text = "\n\n".join(["😀" * 1500] * 2)  # 3000 units each: one chunk would be 6000+
    chunks = telegram.split_text(text)
    assert len(chunks) == 2 and all(len(c.encode("utf-16-le")) // 2 <= 4096 for c in chunks)


def test_a_short_text_is_one_message(http):
    telegram.send_message(TOKEN, "42", "short")
    assert len(http.calls) == 1


# --- sendDocument -------------------------------------------------------------------------------------------

def test_send_document_is_a_multipart_upload_with_the_file_and_a_caption(http, tmp_path):
    f = tmp_path / "dbw-report-2026-10-02.html"
    f.write_bytes("<html>שלום</html>".encode("utf-8"))
    telegram.send_document(TOKEN, "-100123", f, "Report 2026-10-02: ORANGE")
    (c,) = http.calls
    assert c.method == "sendDocument" and c.ctype.startswith("multipart/form-data; boundary=")
    boundary = c.ctype.split("boundary=")[1].encode()
    assert c.body.count(b"--" + boundary) == 4 and c.body.rstrip().endswith(b"--" + boundary + b"--")
    assert b'name="chat_id"\r\n\r\n-100123\r\n' in c.body
    assert b'name="caption"\r\n\r\nReport 2026-10-02: ORANGE\r\n' in c.body
    assert b'name="document"; filename="dbw-report-2026-10-02.html"' in c.body
    assert "<html>שלום</html>".encode("utf-8") in c.body


def test_send_document_keeps_the_caption_inside_telegrams_limit(http, tmp_path):
    f = tmp_path / "r.html"
    f.write_text("x", encoding="utf-8")
    telegram.send_document(TOKEN, "1", f, "c" * 3000)
    caption = http.calls[0].body.split(b'name="caption"\r\n\r\n')[1].split(b"\r\n")[0]
    assert len(caption.decode("utf-8")) == telegram.CAPTION_LIMIT == 1024


# --- errors, redaction, retries -----------------------------------------------------------------------------

def test_an_http_error_is_one_plain_line_and_is_not_retried(http):
    http.script = [fail(400, "Bad Request: chat not found")]
    with pytest.raises(telegram.TelegramError) as e:
        telegram.send_message(TOKEN, "42", "hi")
    assert str(e.value) == "sendMessage: HTTP 400: Bad Request: chat not found" and len(http.calls) == 1


def test_ok_false_on_a_200_is_an_error_line_too(http):
    http.script = [(200, {"ok": False, "description": "odd"})]
    with pytest.raises(telegram.TelegramError, match="sendMessage: HTTP 200: odd"):
        telegram.send_message(TOKEN, "42", "hi")


def test_the_token_never_reaches_an_error_line(http, sleeps):
    http.script = [fail(404, f"Not Found for https://api.telegram.org/bot{TOKEN}/sendMessage")]
    with pytest.raises(telegram.TelegramError) as e:
        telegram.send_message(TOKEN, "42", "hi")
    assert TOKEN not in str(e.value) and "bot<redacted>" in str(e.value)


def test_a_network_error_message_with_the_url_is_redacted(http, sleeps):
    boom = urllib.error.URLError(f"cannot open https://api.telegram.org/bot{TOKEN}/getUpdates")
    http.script = [boom, boom]
    with pytest.raises(telegram.TelegramError) as e:
        telegram.send_message(TOKEN, "42", "hi")
    assert TOKEN not in str(e.value) and str(e.value).startswith("sendMessage: network error")


def test_redact_handles_the_bare_token_and_the_token_shape():
    assert telegram.redact(f"x bot{TOKEN}/y", TOKEN) == "x bot<redacted>/y"
    assert telegram.redact(f"x {TOKEN} y", TOKEN) == "x <redacted> y"
    other = "987654321" + ":" + "B" * 35
    assert other not in telegram.redact(f"seen bot{other}/z", None)


def test_429_waits_retry_after_then_retries_once(http, sleeps):
    http.script = [fail(429, "Too Many Requests: retry after 3", retry_after=3)]
    telegram.send_message(TOKEN, "42", "hi")
    assert len(http.calls) == 2 and sleeps == [3]


def test_429_wait_is_capped(http, sleeps):
    http.script = [fail(429, "Too Many Requests", retry_after=120)]
    telegram.send_message(TOKEN, "42", "hi")
    assert sleeps == [telegram.MAX_WAIT] and telegram.MAX_WAIT == 30


def test_a_second_429_is_the_error(http, sleeps):
    http.script = [fail(429, "Too Many Requests", retry_after=1), fail(429, "Too Many Requests", retry_after=1)]
    with pytest.raises(telegram.TelegramError, match="HTTP 429: Too Many Requests"):
        telegram.send_message(TOKEN, "42", "hi")
    assert len(http.calls) == 2


def test_a_network_error_is_retried_once_after_a_short_wait(http, sleeps):
    http.script = [OSError("connection reset")]
    telegram.send_message(TOKEN, "42", "hi")
    assert len(http.calls) == 2 and len(sleeps) == 1 and 0 < sleeps[0] <= telegram.MAX_WAIT


def test_two_network_errors_are_one_line(http, sleeps):
    http.script = [OSError("connection reset"), OSError("connection reset")]
    with pytest.raises(telegram.TelegramError) as e:
        telegram.send_message(TOKEN, "42", "hi")
    assert str(e.value) == "sendMessage: network error (connection reset)"


def test_a_body_that_is_not_json_is_an_error_line(monkeypatch):
    monkeypatch.setattr(telegram, "_http", lambda url, body, ctype: (502, b"<html>Bad Gateway</html>"))
    with pytest.raises(telegram.TelegramError, match="sendMessage: HTTP 502"):
        telegram.send_message(TOKEN, "42", "hi")


# --- the token ----------------------------------------------------------------------------------------------

def test_token_comes_from_the_environment_first(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("DBW_TELEGRAM_TOKEN=from-file\n", encoding="utf-8")
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", "from-env")
    assert telegram.load_token(tmp_path / ".env") == "from-env"


def test_token_from_the_dotenv_file_ignores_comments_blanks_quotes_and_export(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# a comment\n\nOTHER=1\nexport DBW_TELEGRAM_TOKEN = \"abc:def\"  \nlater=2\n", encoding="utf-8")
    assert telegram.load_token(p) == "abc:def"


def test_dotenv_parser_reads_utf8_and_skips_junk_lines():
    assert telegram.parse_dotenv("naïve=ü\nno equals sign\n=novalue\nA='x'\n") == {"naïve": "ü", "A": "x"}


@pytest.mark.parametrize("text", [None, "", "DBW_TELEGRAM_TOKEN=\n", "OTHER=1\n"])
def test_a_missing_token_is_one_clear_line(tmp_path, text):
    p = tmp_path / ".env"
    if text is not None:
        p.write_text(text, encoding="utf-8")
    with pytest.raises(telegram.TelegramError) as e:
        telegram.load_token(p)
    msg = str(e.value)
    assert "DBW_TELEGRAM_TOKEN" in msg and "docs/telegram.md" in msg and "\n" not in msg


# --- getUpdates -> chats ------------------------------------------------------------------------------------

UPDATES = [
    {"update_id": 1, "message": {"date": 1790000000, "chat": {"id": 111, "type": "private", "first_name": "Shay"}}},
    {"update_id": 2, "message": {"date": 1790003600, "chat": {"id": 111, "type": "private", "first_name": "Shay"}}},
    {"update_id": 3, "message": {"date": 1790001000, "chat": {"id": -100222, "type": "supergroup", "title": "Plant ops"}}},
    {"update_id": 4, "channel_post": {"date": 1790002000, "chat": {"id": -100333, "type": "channel", "title": "News"}}},
    {"update_id": 5, "my_chat_member": {"date": 1790004000, "chat": {"id": -100444, "type": "group", "title": "New"}}},
    {"update_id": 6, "poll": {"id": "no chat here"}},
]


def test_chats_from_updates_dedupes_names_and_dates_each_chat():
    chats = telegram.chats_from_updates(UPDATES)
    assert [c["id"] for c in chats] == [-100444, 111, -100333, -100222]  # newest first
    by = {c["id"]: c for c in chats}
    assert by[111] == {"id": 111, "type": "private", "name": "Shay", "last": 1790003600}
    assert by[-100222]["name"] == "Plant ops" and by[-100222]["type"] == "supergroup"


def test_chat_name_falls_back_to_first_last_then_username_then_blank():
    mk = lambda chat: telegram.chats_from_updates([{"message": {"date": 1, "chat": {"id": 5, "type": "private", **chat}}}])[0]
    assert mk({"first_name": "A", "last_name": "B"})["name"] == "A B"
    assert mk({"username": "ab"})["name"] == "@ab"
    assert mk({})["name"] == ""


def test_get_updates_returns_the_result_list(http):
    http.script = [(200, {"ok": True, "result": UPDATES})]
    assert telegram.get_updates(TOKEN) == UPDATES
    assert http.calls[0].method == "getUpdates"


def test_describe_chat_is_one_line_with_a_utc_date():
    line = telegram.describe_chat({"id": 111, "type": "private", "name": "Shay", "last": 1790003600})
    assert line == "111  private  Shay  last message 2026-09-21 15:13 UTC"


def test_an_invalid_request_error_that_quotes_the_url_is_redacted(monkeypatch):
    def bad(url, body, ctype):
        raise ValueError(f"URL can't contain control characters. {url!r}")
    monkeypatch.setattr(telegram, "_http", bad)
    with pytest.raises(telegram.TelegramError) as e:
        telegram.send_message(TOKEN, "42", "hi")
    assert TOKEN not in str(e.value) and str(e.value).startswith("sendMessage: invalid request")
