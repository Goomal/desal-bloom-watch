# Windows

`dbw schedule install` on Windows imports a Task Scheduler task from XML (`schtasks /Create /XML ... /F`). The XML
sets "run as soon as possible after a scheduled start is missed" (`StartWhenAvailable`), runs as the current user with
the interactive token and least privilege, so it needs **no administrator rights and no password**. Everything in
`dbw/schedule.py` for Windows is tested against a fake `schtasks`, not a real Windows machine. This page is the check
to do by hand once on a real one.

Setup on Windows, from the repository root in PowerShell:

```
py -3 -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\dbw setup
```

## Manual check (6 steps, about five minutes)

1. `.venv\Scripts\dbw schedule install --time <two minutes from now, HH:MM>` prints
   `installed: Task Scheduler task DesalBloomWatch, every day at <time> local time`. If it prints an error, copy it.
2. `.venv\Scripts\dbw schedule status` shows the task, the time and a next run. Also open Task Scheduler
   (`taskschd.msc`), find `DesalBloomWatch`: Triggers shows Daily at that time, Settings shows "Run task as soon as
   possible after a scheduled start is missed" ticked.
3. Wait for the time. `data\dbw-run.log` gains a block that ends with a `RESULT` line, and the report folder gains
   `dbw-report-<date>.html`. (Task Scheduler shows `Last Run Result` 0x0.)
4. Run `dbw schedule status` again: it shows the last result.
5. Missed-start check: `dbw schedule install --time <a time five minutes ahead>`, put the PC to sleep through that
   time, wake it after: the task should run within a minute or two of the wake.
6. `.venv\Scripts\dbw schedule remove` prints `removed: Task Scheduler task`; `schtasks /Query /TN DesalBloomWatch`
   then says it cannot find the task.

If step 3 does nothing: the task runs only while you are logged on. Look at `data\dbw-run.log` and at `Last Run
Result` in Task Scheduler.

## The skill on Windows

`dbw skill install` copies the skill folder as plain files, so it works without symbolic links. A clone of this
repository on Windows may check the committed `.agents/skills/desal-bloom-watch` link out as a plain text file
holding the path (git does this when `core.symlinks` is off, the default without Developer Mode); Codex then does not
see the skill from the clone. Run `dbw skill install --codex` to copy it into `~/.agents/skills` instead.
