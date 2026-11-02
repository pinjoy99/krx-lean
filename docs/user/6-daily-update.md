# 6. Daily update

KRX publishes a trading day's data the next day (it was available by early afternoon KST in
tests). Each update downloads only what's new, rebuilds the LEAN data from `raw/`, and copies it
into the workspace:

```bash
set -a; . ~/.config/krx-lean.env; set +a
krx-lean --root ~/krx-data all
cd ~/krx-workspace && klean data install --root ~/krx-data
klean data status                 # last_date should be the latest trading day
```

`klean data install` adds and replaces files; it never deletes your projects or results.
Recent days that KRX hasn't published yet are retried on the next run. Rerun `rights` and
`krx-info` weekly if you use them.

## Run it automatically

Save as `~/bin/krx-update` and `chmod +x` it:

```bash
#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.krx-lean/venv/bin:$HOME/.dotnet:$PATH"
set -a; . "$HOME/.config/krx-lean.env"; set +a
krx-lean --root "$HOME/krx-data" all
cd "$HOME/krx-workspace" && klean data install --root "$HOME/krx-data"
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

## Results and new data

Old runs keep their results; rerunning a strategy uses the new data. Strategies without
`set_end_date` / `SetEndDate` run up to the newest data, so their figures change after each
update.
