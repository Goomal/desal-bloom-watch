# Daily run

`dbw schedule install` makes the machine run `dbw run` once a day: fetch the newest satellite data, score every
plant in `config.yaml`, write the report. One runner per platform:

| Platform | Runner | What it installs |
|---|---|---|
| macOS | `launchd` | a LaunchAgent, `~/Library/LaunchAgents/com.desalbloomwatch.dbw.plist` |
| Linux | `cron` | one line in your crontab, between two marker comments |
| Windows | `schtasks` | a Task Scheduler task `DesalBloomWatch` ([docs/windows.md](windows.md)) |
| any | GitHub Actions | `.github/workflows/daily.yml`, see the end of this page |

```
dbw schedule install [--time HH:MM] [--runner launchd|cron|schtasks] [--dry-run]
dbw schedule status
dbw schedule remove
```

`--dry-run` prints what would be installed and changes nothing. The runner and the time are recorded in
`config.yaml` (`runner:`, `schedule.time`, see `config.example.yaml`), so `status` and `remove` need no flags.
`dbw setup` also offers the schedule: `--schedule` installs it, `--no-schedule` skips the question, `--yes`
alone does not install one.

## The time

**Default: 07:00 on your local clock.** The report is ready at the start of the workday. `--time HH:MM` overrides it.

Why any morning time works: NOAA publishes each day's data once, and the last of the three data sets we use
arrives at about 21:15 UTC. Measured on 2026-10-02 from the `Last-modified` of the ERDDAP file listings
(`/erddap/files/<dataset>/2026/`, which is when each daily slice landed):

| Data set | When slice D lands | Spread |
|---|---|---|
| DINEOF gap-filled chlorophyll | D+1 21:15 UTC, every day but one since 1 Aug | none |
| CoralTemp sea-surface temperature | D+1 13:40 UTC (median) | up to 14:48 UTC |
| N20 chlorophyll (near real time) | erratic: batches near 02:15, 08:20, 11:30, 17:15, 20:20 UTC | up to 21 days behind through September |

So **any time after about 22:15 UTC (01:15 Israel summer time, 00:15 winter time) gets the newest day there is**,
and two runs between one 22:15 UTC and the next fetch the same data. A run earlier than 22:15 UTC sees the day
before, one day older. That is why the default is the start of the workday and not the middle of the night.

The N20 chlorophyll is the slow one. When it is late the report says so for that plant (its data date is older and
the confidence line shows the age) and a later run picks the slice up.

## Missed runs

- **launchd** (macOS): `StartCalendarInterval` is the calendar-time key. From `man launchd.plist`: "Unlike cron
  which skips job invocations when the computer is asleep, launchd will start the job the next time the computer
  wakes up. If multiple intervals transpire before the computer is woken, those events will be coalesced into one
  event upon wake from sleep." A laptop that was asleep at 07:00 runs the job when it wakes.
- **cron** (Linux): a run is skipped if the machine is off or asleep at that minute. Nothing catches up on wake.
- **schtasks** (Windows): the task is created with "run as soon as possible after a scheduled start is missed"
  (`StartWhenAvailable`), so a PC that was asleep or off at 07:00 runs it at the next start or wake. It runs only
  while you are logged on (no stored password, no admin rights).
- **Powered off the whole day** (cron any time, launchd and schtasks too if the machine stays off): that day has no
  run of its own. The next run makes up for it, see "Catch-up".

## Catch-up

`dbw run` with no `--date` re-fetches the last 10 days of the three scored data sources before it scores, so a
skipped day or a late slice is filled in by the next run. A run with `--date` fetches only that day, as before.
The scheduled run (`--log`) first waits up to 5 minutes for the network: a laptop that wakes at 07:00 often has
no Wi-Fi for the first seconds, and without the wait the run would go partial. The log says `network: up after N s`
when it had to wait. A run you start by hand does not wait.
A slice that arrives more than about 10 days late is not picked up by the daily run; use
`dbw backfill --from <date> --force` for that.

## Where the output goes

- `data/dbw-run.log` in the repository: everything the run printed and a final `RESULT` line, appended every day.
  Read it first when a report did not appear: `tail data/dbw-run.log`.
- `data/dbw-launchd.log` (macOS only): what escapes the log above, such as a Python import error.
- The reports go to the folder in `config.yaml` (`report.out`).

`dbw schedule status` shows whether the job is installed, the time, the next run, and the RESULT line of the last
run. When NOAA cannot be reached the run still scores from the stored history and writes the report with a note
saying so; `status` then shows "partial: upstream unreachable". A failed Telegram send ([telegram.md](telegram.md)) never
stops the report either: `status` shows "partial: telegram failed" and the log has one `telegram: failed for <chat>: <reason>`
line per chat. When both happen it reads "partial: upstream unreachable, telegram failed".

## Things to know

- **Daylight saving.** The job runs at the same local clock time all year. The NOAA arrival is fixed in UTC, so it
  moves by an hour against your clock in spring and autumn; 07:00 stays after it in Israel in both.
- **The repository must stay where it is.** The job holds the absolute path of the repository, its `.venv` and its
  `config.yaml`. If you move the folder, run `dbw schedule install` again.
- **`DBW_DB`** (a database path override) is not passed to the scheduled job; it uses `data/dbw.sqlite` of the
  repository.
- **One job.** Installing again replaces the job. `remove` deletes only this job, never other launchd, cron or Task
  Scheduler entries (the cron block is found by its marker comments).

## GitHub Actions instead

`.github/workflows/daily.yml` runs the same daily job in GitHub's cloud, so no machine of yours has to be on. Copy the
repository to your own GitHub account, then:

1. Settings, Secrets and variables, Actions, Variables: add `DBW_PLANTS` with the plant ids, e.g. `hadera,ashkelon`.
2. Actions tab: enable workflows, then "Run workflow" once to check it.

It runs at 04:00 UTC (07:00 Israel summer time, 06:00 winter time), after the data has landed. Each run checks out the
repository, installs it (`pip install -e .`: the code finds `plants.yaml` next to itself, so it must run from the checkout), sets up the plants (with the bundled percentiles, so setup is short), runs `dbw run` and
uploads the report folder as a build artifact (kept 90 days; download it from the run page). The database in `data/`
is carried from run to run with the Actions cache; if the cache is evicted (GitHub drops caches unused for 7 days) the
run rebuilds the last 45 days and the catch-up fills the rest. Nothing is sent anywhere else. The workflow file has a
commented placeholder for secrets, for the day a channel (Telegram, email) is added. It has not been run by this
project's tests; the test only checks that the file parses and has the expected triggers and steps.
