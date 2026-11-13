# 6. Daily update

KRX publishes a trading day's data the next day (it was available by early afternoon KST in
tests). Each update downloads only what's new, rebuilds the LEAN data from `raw/`, and copies it
into the workspace:

```bash
cd ~/krx-workspace
klean update data            # prints the new date range when done
```

`klean update data` does the whole routine: it reads your keys from `~/.config/krx-lean.env` (if
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

Save as `~/bin/krx-update` and `chmod +x` it:

```bash
#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.krx-lean/venv/bin:$HOME/.dotnet:$PATH"
cd "$HOME/krx-workspace" && klean update data
```

### Linux: cron

`crontab -e`, weekdays at 15:00 KST (cron uses the system time zone; 15:00 KST = 06:00 UTC):

```
0 6 * * 1-5  $HOME/bin/krx-update >> $HOME/krx-update.log 2>&1
```

### WSL2

Cron only runs while WSL is running and, on Ubuntu, needs systemd: add

```
[boot]
systemd=true
```

to `/etc/wsl.conf`, run `wsl --shutdown` in PowerShell, reopen Ubuntu, then
`sudo systemctl enable --now cron` and add the crontab line above. Alternatively, create a
Windows Task Scheduler task that runs `wsl.exe -d Ubuntu-24.04 -- bash -lc ~/bin/krx-update`.

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
