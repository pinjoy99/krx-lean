# 1. Install

Tested on Ubuntu 24.04 and 22.04, natively and under WSL2. About 20–40 minutes, mostly
downloads and the LEAN build. On a Mac, read [macOS](#macos) first.

## WSL2 only: before you start

- Use a WSL2 Ubuntu distribution (`wsl --install -d Ubuntu-24.04` in PowerShell).
- Work inside the Linux file system (`~/…`), **not** under `/mnt/c/…`: file access there is many
  times slower, and LEAN reads thousands of small files.
- Parallel optimizations use memory: if WSL runs out, raise `memory=` in
  `%UserProfile%\.wslconfig` (for example `memory=8GB`) and run `wsl --shutdown`.
- Optional, so `klean gui` and `klean research` open your Windows browser:
  `sudo apt install -y wslu`.

## System packages

```bash
sudo apt update
sudo apt install -y git curl unzip python3 python3-venv libicu-dev
```

(`libicu-dev` is for .NET; on other distributions install git, curl, unzip, Python 3.10+ with
venv, and ICU.)

## .NET 10 SDK

```bash
curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 10.0
echo 'export DOTNET_ROOT="$HOME/.dotnet"; export PATH="$HOME/.dotnet:$PATH"' >> ~/.bashrc
source ~/.bashrc
dotnet --version            # 10.0.x
```

The installer unpacks in `/tmp` (about 1 GB). If `/tmp` is small and it fails with "No space
left on device", run it with `TMPDIR=~/tmp` (after `mkdir -p ~/tmp`) in front of `bash`.

## uv (provides Python 3.11 for LEAN)

LEAN runs Python strategies through pythonnet, which needs CPython **3.11** with its shared
library. Ubuntu 24.04 ships 3.12, so krx-lean gets 3.11 from uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

## krx-lean and klean

```bash
git clone https://github.com/pinjoy99/krx-lean.git ~/krx-lean
python3 -m venv ~/.krx-lean/venv
~/.krx-lean/venv/bin/pip install -e ~/krx-lean
echo 'export PATH="$HOME/.krx-lean/venv/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
krx-lean --help && klean --version
```

Keep `~/krx-lean`: it's installed in editable mode, and `klean` copies the KRX models from it into
new projects. To update later: `git -C ~/krx-lean pull`.

## LEAN

```bash
klean install-lean --dir ~/Lean          # clones LEAN at the tested commit and builds it (2–10 min)
klean install-python --dir ~/.klean/py311   # Python 3.11 + pandas/numpy for LEAN (via uv)
```

`install-lean` uses the LEAN commit krx-lean was tested with; don't build another one unless you
want to test it (see [5. Tools](5-tools.md#updating-lean)). `install-python` prints the Python
library it found (`…/libpython3.11.so`). Packages needed only by some tools are added to that
environment the first time you use them: matplotlib for `klean report`, JupyterLab for
`klean research`.

## macOS

**Experimental.** On Apple Silicon Macs the automated end-to-end check passes on every change
(LEAN build, backtests in C# and Python with identical results, report, research notebook), but
nobody has followed these steps by hand yet; Intel Macs are untested. Please report what you
find. The differences from the Linux steps above:

```bash
xcode-select --install                                   # git (skip if already installed)
curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 10.0
curl -LsSf https://astral.sh/uv/install.sh | sh
echo 'export DOTNET_ROOT="$HOME/.dotnet"' >> ~/.zshrc
echo 'export PATH="$HOME/.dotnet:$HOME/.krx-lean/venv/bin:$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
git clone https://github.com/pinjoy99/krx-lean.git ~/krx-lean
uv venv --python 3.12 ~/.krx-lean/venv                   # macOS's own python3 is too old
uv pip install --python ~/.krx-lean/venv/bin/python -e ~/krx-lean
klean install-lean --dir ~/Lean
klean install-python --dir ~/.klean/py311
```

No `apt` packages are needed, the shell profile is `~/.zshrc`, and `klean gui` /
`klean research` open your default browser. Everything after this page is the same.

Next: [2. Keys and data](2-data.md). Waiting for your KRX key? Try everything on
[synthetic demo data](demo.md) meanwhile.
