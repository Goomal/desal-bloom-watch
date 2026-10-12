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
