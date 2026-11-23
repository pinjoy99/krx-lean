# 6. Daily update

KRX publishes a trading day's data the next day (it was available by early afternoon KST in
tests). Each update downloads only what's new, rebuilds the LEAN data from `raw/`, and copies it
into the workspace:

```bash
cd ~/krx-workspace
klean update data            # prints the new date range when done
```

`klean update data` does the whole routine, and then lets your live paper deployments trade the
new days ([5. Tools](5-tools.md#live-paper-trading-live)). It reads your keys from `~/.config/krx-lean.env` (if
they aren't already in the environment; another file with `--env-file`), runs
`krx-lean --root <data root> all`, and installs the result into the workspace. It uses the data
root you last installed from (`klean install data --root ~/krx-data`); name it once with
`klean update data --root ~/krx-data` if the workspace was set up another way. If the download stops
early (network, quota), run it again. The same by hand:

```bash
set -a; . ~/.config/krx-lean.env; set +a
krx-lean --root ~/krx-data all
cd ~/krx-workspace && klean install data --root ~/krx-data
klean status data            # last_date should be the latest trading day
```

Installing data adds and replaces files; it never deletes your projects or results. Only files
that changed are copied (`… files copied, … unchanged`), so the daily update is quick.
Recent days that KRX hasn't published yet are retried on the next run. Rerun `rights` and
`krx-info` weekly if you use them.

## Run it automatically

Save as `~/bin/krx-update` and `chmod +x` it (use the folder `which klean` shows if yours
differs from `~/.krx-lean/venv/bin`):

```bash
#!/usr/bin/env bash
# Daily: new KRX data, then live paper deployments trade the new day(s).
set -euo pipefail
exec >> "$HOME/krx-update.log" 2>&1
export DOTNET_ROOT="$HOME/.dotnet"
export PATH="$HOME/.krx-lean/venv/bin:$HOME/.dotnet:$HOME/.local/bin:$PATH"
echo "=== $(date)"
cd "$HOME/krx-workspace"
klean update data
klean live status
```

When: KRX publishes a trading day's data the next day, by early afternoon in Korea. Run it
once a day after that; days without new data do nothing, and missed days are caught up.
Deployments on klean's paper broker trade the new days in the same run. **KIS-PAPER**
deployments are skipped here: they trade at KRX's pre-open auction (08:30–08:59 KST) and need
their own schedule ([5. Tools](5-tools.md#kis-paper-a-korea-investment-모의투자-paper-account)).

| You are in | Run at (local) | Gets |
|---|---|---|
| Korea (KST) | 15:00 | the previous trading day |
| US Eastern (EST/EDT) | 07:30 | the trading day that ended in Korea ~18 h earlier (Monday: Friday's) |
| UTC | 06:00 | the previous trading day |

### WSL2: Windows Task Scheduler (recommended)

Cron inside WSL only runs while WSL is running, and WSL stops soon after its last terminal
closes. Task Scheduler starts WSL itself and uses the Windows clock. In PowerShell
(`wsl -l -v` shows your distribution's name; replace `<you>` with your Linux user name):

```powershell
schtasks /Create /TN "krx-update" /SC DAILY /ST 07:30 /TR "wsl.exe -d Ubuntu -e /home/<you>/bin/krx-update"
schtasks /Run /TN "krx-update"          # try it now; then `tail ~/krx-update.log` in Ubuntu
```

In Task Scheduler, the task's Properties can make it run while you're logged out and wake the
computer for it.

### Linux (or WSL left running): cron

Cron uses the system time zone (`date` shows it; `sudo timedatectl set-timezone
America/New_York` changes it). `crontab -e`:

```
30 7 * * *  $HOME/bin/krx-update
```

On WSL, cron also needs systemd: add `[boot]` / `systemd=true` to `/etc/wsl.conf`, run
`wsl --shutdown` in PowerShell, reopen Ubuntu, then `sudo systemctl enable --now cron`.

## After updating krx-lean itself

```bash
cd ~/krx-workspace
klean update klean           # git pull of your krx-lean clone (~/krx-lean)
klean update all             # the same, then LEAN (only if krx-lean now uses another commit),
                             # then the data, then a check of the projects' models
```

`klean update all` never touches your projects; it only reports which ones have an older copy
of the models. Each project keeps the copy of the KRX models
(`krx_models.py` / `KrxModels.cs`) it was created with, including its tax rates and tick tables.
`klean backtest` and `klean doctor` tell you when a project's copy differs from the current
models:

```bash
klean status models          # current / differs, per project
klean update models Top20    # replace the copy (yours is kept as krx_models.py.bak)
klean update models --all
```

If you edited the models yourself, "differs" is expected; update only if you want krx-lean's
version back.

## Results and new data

Old runs keep their results; rerunning a strategy uses the new data. Strategies without
`set_end_date` / `SetEndDate` run up to the newest data, so their figures change after each
update.
