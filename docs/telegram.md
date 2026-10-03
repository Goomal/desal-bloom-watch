# Telegram

Each day's run can send the report to Telegram: the short message (the `.txt`, as the message text) and the HTML
report as an attached file. It goes to the chats you list in `config.yaml`, today your own private chat with your
own bot. Nothing is sent to anyone else, and the code calls no model: it only posts the files the report already wrote.

## Set it up (three steps, then one command)

1. **Make a bot.** In Telegram, open a chat with **@BotFather**, send `/newbot` and answer its two questions. It
   replies with a token that looks like `<digits>:<letters>`.
2. **Put the token in the `.env` file** that sits next to `config.yaml` (copy `.env.example` to `.env` if you have
   none), as one line:

   ```
   DBW_TELEGRAM_TOKEN=<your token>
   ```

   Edit the file yourself, in your own editor. `.env` is gitignored. The token is a password for the bot: do not
   paste it into a chat, an issue or a command line, and do not put it in `config.yaml`. (Setting
   `DBW_TELEGRAM_TOKEN` in the environment works too and wins over the file.)
3. **Message the bot.** Open your new bot in Telegram and press Start (or send any text).

Then:

```
dbw telegram chat-id --write     # finds your chat id and saves it in config.yaml
dbw send-test telegram           # sends "Desal Bloom Watch test: the bot can reach this chat."
dbw send-test telegram --latest  # also sends the newest report's short message and HTML file
```

`dbw setup --telegram` does the same inside setup (it prints the three steps, waits for you to do them, then runs
the chat-id step); plain `dbw setup` asks "Send the daily report to Telegram? [y/N]", and `--yes` says no.

`dbw telegram chat-id` without `--write` only lists the chats that have messaged the bot: id, type, name and the
date of the last message. If it says there is nothing, send your bot a message first (Telegram keeps unread
messages for 24 hours). With `--write` it adds the id to `channels.telegram.chat_ids` and turns telegram on; when
several chats are listed it never picks for you: add `--pick <id>`.

## What `config.yaml` holds

```yaml
channels:
  telegram:
    enabled: true
    chat_ids: [123456789]
```

`chat_ids` is a list of whole numbers (or numbers in quotes); it must not be empty while `enabled` is true.

## What is sent, and when

At the end of every `dbw run` (the scheduled job, or by hand), after the report files are written, each chat gets:

1. one message with the text of `dbw-report-<date>.txt` (over 4,096 characters it is split at paragraph breaks;
   today it is under 3,500);
2. the file `dbw-report-<date>.html`, with the first line of the short message (the title and date) as caption.

Telegram needs both files, so when `report.formats` in your config lacks `txt` or `html` the run writes them anyway.
No PNG is sent: the html already carries the map inside it (a `data:image/png;base64,` image), so it shows
when the file is opened on its own. The separate `.png` is still written to the folder.

**For the email channel (not built yet):** Gmail and some other mail clients block `data:` images, so an email
should attach the PNG inline by Content-ID (`cid:`) and point the `<img>` at it, not reuse the embedded copy.

## When a send fails

The report is already written and stays. The run logs one line per chat, `telegram: failed for <chat>: <method>,
HTTP code, Telegram's description` (for example `sendMessage: HTTP 403: Forbidden: bot was blocked by the user`),
ends with `RESULT partial: telegram failed`, and `dbw schedule status` shows that result. It retries once, after a
short wait, on a network error or on Telegram's "too many requests" (429, honouring its `retry_after`, at most 30
seconds); other 4xx errors are not retried. A missing token is the same kind of failure: `telegram: failed: no
Telegram bot token: set DBW_TELEGRAM_TOKEN ...`. The token is never written to the log or to any error line.

## Add a group later

1. Add your bot to the group in Telegram.
2. Send a message in the group (if the bot's privacy mode is on, which is Telegram's default, send `/start@<botname>`
   or mention the bot, so that it sees something).
3. `dbw telegram chat-id` now lists the group too (its id is negative, like `-100...`). Save it next to your private
   chat: `dbw telegram chat-id --write --pick <the group id>`.
4. `dbw send-test telegram` sends the test message to every chat in the list.

To stop sending to a chat, delete its id from `chat_ids`; set `enabled: false` to stop sending altogether.
