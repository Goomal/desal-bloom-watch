# Subscriptions: Telegram sign-up bot (`/add`, `/remove`) — design

Date: 2026-10-12 · Status: design approved in conversation, not yet implemented

## 1. Where we are (session notes, 2026-10-12)

Repo: https://github.com/Goomal/desal-bloom-watch (branch `main`, commit `f57d966`).

Checked on Windows 11, Python 3.12:

- Install: `py -3.12 -m venv .venv` then `.venv\Scripts\pip install -e ".[dev]"`. Works.
- Tests: `$env:PYTHONUTF8="1"; .venv\Scripts\python -m pytest -q` gives 550 passed, 10 skipped, 1 failed.
  - The failure is `tests/test_skill.py::test_codex_link_is_a_relative_symlink_to_the_skill_folder`. It comes from the
    checkout, not the code: git on Windows has `core.symlinks=false`, so `.agents/skills/desal-bloom-watch` was
    checked out as a text file.
  - Fix: turn on Windows Developer Mode, then `git config core.symlinks true` and `git checkout -- .agents`.
- Real run: `dbw setup --plants "hadera,ashkelon,eilat" --language en --yes --no-schedule --no-telegram`.
  - It fetched 45 days from NOAA in about 3.5 minutes with 0 failed days, and wrote the html, md, png and txt reports.
  - Result: Hadera red, Ashkelon red, Eilat yellow.
- `dbw doctor`: all sources OK.
- Not tried yet: `dbw schedule install` (Windows Task Scheduler) and Telegram delivery.
- Dev tip: set `PYTHONUTF8=1` (as CI does) before running dbw or pytest on Windows.

## 2. Goal

Send the daily report to people who ask for it. Each person chooses which plants and which language they get. The
admin (the repo owner) can add and remove people. Each person can remove themselves.

## 3. Decisions

| Topic | Decision |
|---|---|
| Channels now | **Telegram only** |
| Email | **Dropped.** Not wanted |
| WhatsApp | **Phase 2**, through the official Meta WhatsApp Cloud API (needs a Meta Business account, a dedicated number, an approved message template, a webhook behind a Cloudflare Tunnel, and a small cost per message). The unofficial WhatsApp Web route was rejected because it breaks WhatsApp's terms and the number can be banned |
| Where `/add` is typed | **Both** in Telegram (to the bot) and on the computer (`dbw subscribers add`) |
| Who can sign up | **Open self-sign-up.** Anyone who messages the bot can subscribe. The admin is notified of each new subscriber and can remove them |
| Connecting on Telegram | **The person messages the bot first.** A bot cannot message someone who has not opened it |
| Language | **Per subscriber** (en / he / ar) |
| How the bot listens | **Always-on listener** `dbw bot` on this PC, started at login by Task Scheduler. It answers only while the PC is on |
| Storage | **New tables in the existing SQLite database** `data/dbw.sqlite` |
| Who sends the daily report | The **existing daily run** (`dbw run`). The bot only handles conversations |

## 4. Data

Table **subscribers**, one row per person (or group) per channel:

| Field | Notes |
|---|---|
| `id` | |
| `name` | given by the person (or the admin) |
| `channel` | `telegram` now, `whatsapp` later |
| `address` | Telegram chat id. A group's id is negative |
| `plants` | list of plant ids from `plants.yaml` |
| `language` | `en` / `he` / `ar` |
| `status` | `active` / `removed` |
| `added_by` | `self` / `admin` |
| `created_at`, `removed_at` | |

Table **contacts** lists every chat that has messaged the bot (chat id, name, last message time). `/add` and
`dbw subscribers add` pick people from it. It is needed because only the bot may read incoming messages; a second
reader would compete with it for the same messages.

Table **conversations** records where each chat is in a questionnaire, so a bot restart doesn't lose anyone's place.

The admin is set in `config.yaml` as `channels.telegram.admin_ids: [<chat id>]`, with a command that fills it in, in
the same way as `dbw telegram chat-id --write`.

The existing `channels.telegram.chat_ids` keep receiving the admin's own full report, exactly as today.

## 5. Conversations (Telegram, answers are buttons)

| Who | Sends | What happens |
|---|---|---|
| A new person | anything, e.g. `/start` | Questions, in order: **language** (EN / עברית / العربية), then the rest in that language: **name**, then **plants** (tap to tick, then Done), then confirm. They are subscribed at once. The admin gets "New subscriber: Dana. Hadera, Ashkelon. Hebrew" with a [Remove] button |
| A subscriber | `/start` again | Buttons: change plants, change language, or stop |
| A subscriber | `/remove` or "stop" | "Stop the daily report? [Yes] [No]". On Yes they are removed and the admin is notified |
| The admin | `/add` | A list of contacts who are not subscribed, plus "this chat" (so you can add a group). Pick one, then answer the plants and language questions for them |
| The admin | `/remove` | All subscribers as buttons. Pick one and confirm; the person is told "You've been removed" |
| The admin | `/list` | Every subscriber with their plants and language |
| Anyone | `/help` | Short help, in their language |

The bot's own texts go into the existing `dbw/locales/{en,he,ar}.json`.

On the computer: `dbw subscribers list | add | remove | export`. `add` asks the same questions in the terminal and
picks the person from **contacts**. `export` writes the list to a file as a backup.

## 6. Runtime

**`dbw bot`**
- Waits for new Telegram messages (`getUpdates` with a long timeout), using only the standard library and reusing
  `dbw/channels/telegram.py` (inline keyboards and `answerCallbackQuery` are new).
- A lock file makes sure only one bot runs at a time. It writes a log to `data/dbw-bot.log`.
- `dbw bot install | uninstall | status`. On Windows this creates a Task Scheduler task that starts at login and
  restarts on failure. On macOS it uses launchd, and on Linux systemd or cron, following `dbw/schedule.py`.

**The daily run (`dbw run`), changes:**
1. The plants to fetch become the `config.yaml` plants plus the plants of every active subscriber.
2. It groups active subscribers by (plants, language), then builds each group's report once with
   `report.build_report(conn, boxes, plant_ids, day)` and `report.write_report(..., lang=...)`. The files go to
   `reports/subscribers/<date>/<group>/`. The admin's own report is unchanged.
3. It sends each subscriber the short message and the HTML file through `telegram.send_report`.

**Sending interface:** `send(address, text, html_path)`. Telegram is the first implementation; WhatsApp becomes
another one later, plus its own webhook receiver.

## 7. Failures

- If one subscriber's send fails, it is logged and the others still get theirs. The run is then "partial: telegram
  failed for N of M" in `dbw schedule status`.
- **Telegram error 403** (the person blocked the bot or deleted their account): the subscriber is removed
  automatically and the admin is told.
- If the bot is down, daily reports are not affected (the daily run sends them). Commands wait until the bot is
  back; Telegram keeps unread messages for 24 hours.
- The bot token never appears in logs, using the existing `telegram.redact`.
- `dbw doctor` adds two checks: whether the bot is running, and whether `admin_ids` is set.

## 8. Tests (offline, run on Linux, macOS and Windows CI)

- The questionnaire, step by step, using fake updates through the existing `telegram._http` test hook. This
  includes picking up again after a restart.
- Admin-only commands are refused for people who are not admins.
- Adding, removing and changing subscribers in the database; the export.
- The daily run: which plants it fetches, grouping by (plants, language), one subscriber failing without stopping the
  rest, and automatic removal after a 403.
- The XML for the bot's Task Scheduler task, and the install arguments.

## 9. Out of scope (for now)

- Email (dropped).
- WhatsApp (phase 2).
- Per-person alert thresholds ("only message me on orange or red"). Everyone gets the daily report.
- A web sign-up form.

## 10. Next steps

1. Review this spec.
2. Write the implementation plan (superpowers `writing-plans`), then build it on a feature branch.
3. Before testing it for real: create the bot with @BotFather, put `DBW_TELEGRAM_TOKEN` in `.env`, and set
   `admin_ids`.

## Fact ownership

Each fact lives in one place; everything else reads it from there.

| Fact | Existing surfaces | Owner |
|---|---|---|
| Who is subscribed, to which plants, in which language | none (grep: `subscriber`) | `subscribers` table (new `dbw/subscribers.py`) |
| Chats that have messaged the bot | `dbw/channels/telegram.py` (chats_from_updates, read at setup only) | `contacts` table, written by `dbw bot` |
| Where a chat is in a questionnaire | none (grep: `conversation`) | `conversations` table |
| Which Telegram updates were handled | none (grep: `offset`) | `bot_state` table (`telegram_offset`) |
| Who the admin is | `dbw/config.py` (channels.telegram) | `config.yaml` `channels.telegram.admin_ids` |
| The admin's own report chats | `dbw/config.py` (telegram_chat_ids) | `config.yaml` `channels.telegram.chat_ids` (unchanged) |
| The bot token | `dbw/channels/telegram.py` (load_token) | `.env` `DBW_TELEGRAM_TOKEN` (unchanged) |
| Report content per plants and language | `dbw/report.py` (build_report, write_report) | `dbw/report.py` (unchanged) |
| Result of a daily run | `dbw/schedule.py` (run_logged, partial) | `data/dbw-run.log` RESULT line |

## Invariants

I1 A chat has at most one active subscription at a time.
I2 A subscriber gets at most one daily report per day, and a dated `dbw run --date` never sends to subscribers.
I3 One subscriber's failed send never stops the others; the run is then "partial: telegram failed for N of M".
I4 Telegram error 403 removes the subscriber and tells the admin.
I5 Only an `admin_ids` user can run `/add`, `/list`, the admin `/remove`, or press the admin's buttons.
I6 Only one `dbw bot` polls Telegram at a time.
I7 The bot token never appears in a log line or an error message.
I8 The admin's own report (`chat_ids`, the files in `reports/`) is unchanged by subscriptions.
