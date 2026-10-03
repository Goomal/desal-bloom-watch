---
name: desal-bloom-watch
description: Set up, run, schedule and explain the Desal Bloom Watch satellite chlorophyll early-warning report for Israeli seawater desalination plants. Use when the user wants to choose plants and an output folder, run today's report, run it every day automatically, understand a level or reason line in a report, or add a plant to the registry.
argument-hint: "[setup|run|schedule|explain|add-plant]"
---

# Desal Bloom Watch

Daily satellite early-warning for algal blooms near Israeli desalination intakes. The Python in
this repo does all the work (fetching, scoring, rendering). **You only drive the `dbw` commands and
explain the output.** Never score, never guess a level, never call a model from the code.

Run every command from the repository root (the folder holding `plants.yaml`). If `dbw` is not on
the path, use the one in the virtual environment: `.venv/bin/dbw` on macOS and Linux,
`.venv\Scripts\dbw` on Windows (and `.venv\Scripts\pip` for pip). If there is no `.venv`:
macOS and Linux: `python3 -m venv .venv && .venv/bin/pip install -e .`;
Windows: `py -3 -m venv .venv` then `.venv\Scripts\pip install -e .`. The other examples in this file
write `dbw`; use whichever form fits the OS.

A level is an early-warning signal for the water near the intake, not a measurement inside the
plant. Say so whenever you summarise one.

## Start here

The user may pass one word after the skill name (`/desal-bloom-watch setup` in Claude Code,
`$desal-bloom-watch setup` in Codex). With an argument, go straight to its section: `setup` is
section 1, `run` is section 2, `explain` is section 3, `add-plant` is section 4, `schedule` is section 5,
`telegram` is section 6.

With no argument, ask one single-choice question, "What do you want to do?", with four options:
"Setup", "Run today's report", "Schedule daily run", "Explain a report". The question text says that
adding a plant is not in the list but is one answer away: choose "Other" and type `add-plant` (or `telegram`). Put
"(Recommended)" and the first position on "Setup" when `config.yaml` is missing, otherwise on "Run
today's report". Without the `AskUserQuestion` tool (Codex), print the same four choices as a numbered
plain-text list, add a fifth line "add-plant", and wait for the number or the word. Then go to that
section.

## 1. Setup ("set me up", "choose my plants")

Setup is a guided questionnaire with clickable choices. **Use the `AskUserQuestion` tool** (checkboxes
for multi-select, radio buttons for single choice) for every step. Run nothing until step 4. Without
that tool (Codex has no checkbox picker), ask the same questions as plain text, one per message,
and wait for each answer.

`AskUserQuestion` limits: 1-4 questions per call, 2-4 options per question. "Other" (free text) is
always added, so do not add it yourself. A recommended option goes first, with "(Recommended)" in its
label.

1. **Existing config (only if `config.yaml` exists).** Read it, then ask one single-choice question
   that names its plants and folder. The options are "Keep it, run today's report" (Recommended, go
   to section 2) and "Replace it".
2. **Plants (one call, multi-select).** List the plants, grouped by sea and north to south: `dbw plants --json`
   (`dbw plants` prints the same as text). Build one multi-select question per sea, in that order. A sea with more than 4 plants is split
   north to south into the fewest groups of at most 4, as even as possible. Name the groups by sea
   and part (header e.g. "Med north", "Med south", "Red Sea"). A group with only one plant gets a
   second option, "None". In larger groups, the user picks "Other" and types "none" to skip.
   - Option label: the plant name. Description: its id, plus "shares 4 km satellite cells with
     <others>" for Sorek A, Sorek B and Palmachim.
   - Question text says that upstream sentinel boxes are added automatically.
   - If there are more than 4 groups, ask the rest in a second call.
   - If the user picked no plant at all, ask again. There is no default.
3. **Folder, map, language and daily run (one call, four single-choice questions).**
   - Report folder: `./reports` (Recommended; inside this repository, gitignored) and
     `~/Documents/desal-bloom-watch-reports`. "Other" takes any path.
   - Map: "Plain map" (Recommended; offline, always works) and "NASA true-colour background"
     (`--basemap gibs`; fetches one public image per report, and falls back to the plain map with
     a reason if the fetch fails).
   - Report language: "English" (Recommended, `en`), "עברית" (`he`) and "العربية" (`ar`). It sets the
     words of the html, markdown and short-text reports. Map labels, numbers, units, box ids and
     dataset names stay English.
   - Daily run: "Every day at 07:00 (Recommended)", "Pick another time" (ask a follow-up for the local
     time as HH:MM on a 24-hour clock, or take it from "Other") and "Not now". It installs a job on this
     computer that runs the report every day (launchd on macOS, cron on Linux, Task Scheduler on
     Windows); section 5 explains it. 07:00 is the local default, after the satellite data has landed.
3b. **Telegram (a second call, one single-choice question).** Ask it right after the daily-run question, as its
   own call because one call holds at most four questions. "Send the daily report to Telegram?" with the options
   "Yes" and "Not now" (Recommended when the user has not mentioned Telegram). It sends the short message and the
   HTML report to the user's own Telegram chat every day. A "Yes" is carried out in section 6 **after** the setup
   command has finished, because the user has to make a bot and put its token in a file first: do not pass
   `--telegram` to `dbw setup`.
4. **Confirm (one single-choice question).** The question shows the chosen plants, folder, map,
   language, daily run and Telegram (yes or not now), the exact command, and that it takes a few minutes (it loads the bundled seasonal percentiles,
   then fetches the last 45 days). The options are "Go" (Recommended) and "Change something", which
   goes back to the step the user names. On Go, run:
   `dbw setup --plants <id,id> --out <folder> --language <en|he|ar> [--basemap gibs] --yes`
   plus `--schedule` (with `--time HH:MM` for another time) when the user chose a daily run, or
   `--no-schedule` when not. Without either flag `--yes` installs no schedule.
   It writes the gitignored `config.yaml`, loads the bundled percentiles for those plants and their
   sentinels, fetches the last 45 days (resumable) and writes the first report. Use
   `--full-history` (rebuilds the percentiles from six years of NOAA history, about an hour) only
   if the user asks for it. The numbers are explained in `docs/percentile-export.md`.
5. **Result.** Give the report files it printed, then summarise the markdown report as in
   section 3. If the user said "Yes" to Telegram, go on to section 6 now.

## 2. Run on demand ("what is the situation today?")

- Fetch today's data and write the report: `dbw run --date <YYYY-MM-DD>` (UTC date; satellite data
  lags 1-2 days, so the newest data date can be earlier than the report date, and the report
  header says which).
- Re-render a date already in the database, without fetching: `dbw report --date <YYYY-MM-DD>`
  (`--plants a,b`, `--format html,md,png,txt`, `--out <dir>`, `--basemap none|gibs`,
  `--language en|he|ar` are optional; the language otherwise comes from `config.yaml`).
- Health check: `dbw doctor`.
- Without `--date`, `dbw run` fetches the last 10 days again before it writes the report, so a day that
  was missed is filled in. If NOAA cannot be reached it says so in one line and scores from the stored
  data; the report then carries a note about it.

Files land in the configured folder as `dbw-report-<date>.html`, `.md`, `.png` and `.txt`. The
`.txt` is the short message: a header line (title and date), exactly two sentences per plant (worst first) and one
closing line, plain text, ready to paste into a chat or an email.

## 3. Explain a report ("why is Eilat orange?")

Explain in the language the user writes in, whatever language the report file is in (a Hebrew or
Arabic report can be explained in English and the other way round). Keep numbers, units, box ids,
dataset names and level words as the report writes them.

1. Read the markdown report for the date: `<out folder>/dbw-report-<date>.md`. If it is missing,
   run `dbw report --date <date>` first.
2. Read `docs/scoring.md` for the rules behind the level words, and `docs/reading-the-report.md` for the
   report's layout: plain summary and one card per plant on top, then "Technical details", then the
   appendix "How to read this report" (colour key and terms).
3. Explain per plant, worst first, using only what the report says. Start from the plain card (what it
   means, compared with normal, how sure) and the "Changed since yesterday" line: when it says the
   satellite changed, say that the two days are not directly comparable. Take the numbers below from
   "Technical details":
   - the level and its reason lines;
   - the value against its seasonal percentiles (P50/P90/P97 for that time of year);
   - the source and its data date, and the data confidence; a **GREY** plant has no usable data and
     the report states why (cloud, no pass, gap) - never turn grey into green;
   - an **upstream signal** label ("ORANGE (upstream signal: tiran >= 1.5x P90; eilat itself is
     yellow)", or its Hebrew or Arabic wording) means a sentinel box further upstream raised the level, not the plant's own box.
     Say this in plain words;
   - the **shared pixel** flag means two plants read the same 4 km satellite cells, so their
     numbers are not independent.
4. Close with the disclaimer from the report: satellite chlorophyll is an early warning, not a
   measurement at the intake or inside the plant. Do not invent causes, forecasts or numbers that
   are not in the report.

## 4. Add a plant ("add plant X")

The registry is `plants.yaml`; its header documents every field. Rules, all hard:

- **Public sources only.** Every non-null field needs a public URL under that plant's `sources:`
  map. A field with no public source is `null`.
- **Never invent coordinates**, an intake box or a capacity. If the intake location is not
  published, ask the user for a public source or leave the field null / use
  `intake_box_basis: estimated` with the reasoning written out.
- Two routes: a private/corrected entry goes in `plants.local.yaml` (same schema, gitignored,
  never committed); a public addition goes in `plants.yaml` as a pull request with the URLs.
- After editing, validate: `.venv/bin/python scripts/check_registry.py plants.yaml`, then
  `dbw doctor`, then `dbw setup --plants <old,new> --out <folder> --yes` to backfill the new box.
- Ask the user for the facts and the URLs; do not fill them from memory.

## 5. Schedule ("run it every day")

The daily run is a job on this computer: launchd on macOS, cron on Linux, Task Scheduler on Windows.
The default time is 07:00 local: the satellite data lands about 22:15 UTC, once a day, so any later
time sees the newest day. If the machine was asleep at the time, launchd and Task Scheduler run it on
wake; cron does not. A machine that is off all day skips that day and the next run fills it in.

1. Check what is there: `dbw schedule status`. It shows whether a job is installed, its time, the next
   run and the result of the last one. Say that in plain words.
2. Ask one single-choice question (without `AskUserQuestion`, as a numbered plain-text list), "What should the daily
   run do?", with the options that fit: "Every day at 07:00 (Recommended)" or, when a job exists,
   "Keep it"; "Pick another time"; "Remove it" (only when a job exists); "Not now".
3. Run the matching command: `dbw schedule install --time HH:MM` (add `--dry-run` first if the user wants
   to see what it will install), or `dbw schedule remove`. It needs `config.yaml`; run section 1 first
   if it is missing. Installing again replaces the job.
4. Tell the user where to look when a report did not appear: `data/dbw-run.log` in the repository, one
   block per run ending in a `RESULT` line. `docs/schedule.md` has the rest, `docs/windows.md` the check
   for Windows. Do not invent a time: the user chooses it.

## 6. Telegram ("send the report to Telegram")

Each daily run can send the short message (the `.txt`, as the message text) and the HTML report (as a file) to the
user's Telegram chat. Setup is three steps by the user, then two commands by you.

**Never ask the user to paste the bot token into the chat. Never read the `.env` file (no `cat`, `grep`, `head`,
Read, or printing the variable) and never put the token on a command line.** The user edits `.env` in their own
editor. The token is a password for the bot.

1. Check what is there: `config.yaml` has `channels.telegram` (`enabled`, `chat_ids`) when it is set up. Reading
   `config.yaml` is fine; it holds no secret. `dbw send-test telegram` is the real check.
2. Tell the user the three steps, in plain words, and wait for them:
   1. In Telegram, message **@BotFather**, send `/newbot` and answer its questions; it gives a token.
   2. Put the token in the file `.env` next to `config.yaml` (copy `.env.example` to `.env` if there is none), as
      one line `DBW_TELEGRAM_TOKEN=<the token>`, by editing the file themselves. `.env` is gitignored.
   3. Open the new bot in Telegram and send it any message (press Start).
   Then ask one single-choice question, "Is the token in `.env` and have you messaged the bot?", with the options
   "Done" and "Not now". Without `AskUserQuestion`, ask it as plain text.
3. On "Done", run `dbw telegram chat-id`. It lists the chats that have messaged the bot (id, type, name, last
   message). If it says nothing was found, ask the user to message the bot again and re-run. If it names the
   missing token, say so in one line and go back to step 2: do not look at the file.
4. Save the chat: `dbw telegram chat-id --write`. With several chats it refuses to choose: ask which one, then
   `dbw telegram chat-id --write --pick <id>`. Several `--write` runs build a list.
5. Prove it: `dbw send-test telegram` sends "Desal Bloom Watch test: the bot can reach this chat." to each chat,
   and `--latest` also sends the newest report's message and HTML file. Say in one line whether each chat said ok.
6. A daily run now sends the report after writing it. A failed send never stops the report: it shows as `partial:
   telegram failed` in `dbw schedule status` and as a `telegram: failed for <chat>: <reason>` line in
   `data/dbw-run.log`. The send needs the `txt` and `html` files, so the run writes them even when `report.formats`
   leaves them out. No PNG is sent.

**Add a group later:** the user adds the bot to the group and writes a message there (with Telegram's default
privacy mode, `/start@<botname>` or a mention), then `dbw telegram chat-id` lists the group (its id is negative)
and `dbw telegram chat-id --write --pick <group id>` adds it next to the private chat. `docs/telegram.md` has the
same steps for a human.

## Install the skill

The skill file lives at `skill/SKILL.md` in this repo. Claude Code loads a skill from a folder
named after it. **First choice, from the repository root, any OS:** `dbw skill install` copies it to
`~/.claude/skills/desal-bloom-watch`. Add `--codex` to copy it to `~/.agents/skills/desal-bloom-watch`
too (Codex), `--project` to install under the current folder instead of your home folder, and
`--force` to replace an existing install (it refuses without it, and re-run it with `--force` after
`git pull`). It copies plain files, so it needs no symbolic link. Then start a new session.

The alternatives, by link instead of copy:

- All your projects (user level). Run it from the repository root, because the link takes its target
  from the current folder; run from anywhere else, it points at a `skill/` that does not exist:
  `cd /path/to/desal-bloom-watch && mkdir -p ~/.claude/skills && ln -s "$PWD/skill" ~/.claude/skills/desal-bloom-watch`
- Only this project, also from the repository root:
  `mkdir -p .claude/skills && ln -s "$PWD/skill" .claude/skills/desal-bloom-watch`
  (`.claude/` is gitignored, so this stays local).

Check the link with `ls ~/.claude/skills/desal-bloom-watch/SKILL.md`.

### Codex

The same file works in Codex, which reads `SKILL.md` with `name` and `description` and ignores other
frontmatter keys such as `argument-hint`. This repository ships a committed relative link,
`.agents/skills/desal-bloom-watch -> ../../skill`, and Codex scans `.agents/skills` at the repository
root, so in a clone of this repo the skill loads with no install step. For other folders, link it
into the user-level folder from the repository root:
`mkdir -p ~/.agents/skills && ln -s "$PWD/skill" ~/.agents/skills/desal-bloom-watch`

On Windows git may check that committed link out as a plain text file holding the path (when
`core.symlinks` is off), and Codex then does not find the skill in the clone: use
`dbw skill install --codex` instead.

Invoke it as `$desal-bloom-watch setup` (or `/skills` and pick it). Codex has no checkbox picker, so
there the questions come as the plain one-question-per-message fallback described in section 1.

Use `cp -R skill ~/.claude/skills/desal-bloom-watch` for a copy instead of a link (re-copy after
`git pull`). Then start a new Claude Code session and type `/desal-bloom-watch setup` at the
Claude prompt. It is a Claude Code command, not a shell command.
