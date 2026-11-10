"""klean: `klean <command>` (or `python -m klean <command>`).

    klean install-lean  [--dir ~/Lean]                  clone LEAN (tested commit) and build it
    klean install-python [--dir ~/.klean/py311]         Python 3.11 env with pandas/numpy for LEAN
    klean init [DIR] --lean ~/Lean [--python-venv ...]  workspace: klean.json + data/ (LEAN config files)
    klean data install lean.zip | --root DATA_ROOT | --demo   KRX data (or SYNTHETIC demo data) into data/
    klean data status                                   KRX data range, securities, indices
    klean project-create NAME [--language] [--template] project with the KRX models next to it
    klean project-delete NAME                           delete a project and its backtests
    klean backtest NAME [--parameter K V] [--extra-config K V] [--backtest-name N] [--output DIR]
    klean optimize NAME --parameter P MIN MAX STEP [...] [--target T] [--constraint "Drawdown < 25"]
    klean report [RUN] [--report-destination F] [--pdf]  LEAN's HTML report for a run (default: latest)
    klean research NAME [--port N] [--no-browser]       JupyterLab with LEAN's QuantBook on the workspace's data
    klean logs NAME|RUN [--console] [--tail N]          a run's algorithm log (or LEAN's console output)
    klean compare RUN RUN [...] [--all]                 statistics and equity curves side by side
    klean config list | get KEY | set KEY VALUE | unset KEY
    klean lean status | update [--commit C]             the LEAN build used by the workspace
    klean update [--root DATA_ROOT]                     download new days, rebuild, install into the workspace
    klean models status | update NAME... | update --all the projects' copies of the KRX models
    klean doctor                                        check the setup
    klean gui [--port N] [--no-browser]                 local web page: projects, runs, charts, compare
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from klean import __version__, projects, results
from klean.backtest import backtest
from klean.workspace import (LEAN_COMMIT, LEAN_CONFIG_DIRS, LEAN_OPTIONAL_FILES, LEAN_REPO, PYTHON_PACKAGES,
                             WORKSPACE_KEYS, KleanError, REPO_ROOT, Workspace, check, dotnet, find_python_dll,
                             git_commit, run, venv_python)


def checkout_and_build_lean(target: Path, commit: str) -> None:
    if not (target / ".git").exists():
        target.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "-q", str(target)])
        run(["git", "-C", str(target), "remote", "add", "origin", LEAN_REPO])
    run(["git", "-C", str(target), "fetch", "-q", "--depth", "1", "origin", commit])
    run(["git", "-C", str(target), "checkout", "-q", "FETCH_HEAD"])
    run([dotnet(), "build", str(target / "Launcher" / "QuantConnect.Lean.Launcher.csproj"), "-c", "Release",
         "-nologo", "-v", "q"])
    if (target / "Report" / "bin" / "Release" / "QuantConnect.Report.dll").exists():   # built by `klean report`
        run([dotnet(), "build", str(target / "Report" / "QuantConnect.Report.csproj"), "-c", "Release",
             "-nologo", "-v", "q"])


def cmd_install_lean(args) -> None:
    target = Path(args.dir).expanduser().resolve()
    checkout_and_build_lean(target, args.commit)
    print(f"LEAN {args.commit[:7]} built in {target}. Next: klean init --lean {target}")


def base_python311(given: str | None) -> str:
    """The CPython 3.11 to build the environment from: --python, else uv's (installed if needed;
    it has the shared libpython pythonnet needs), else python3.11 on the PATH."""
    if given:
        return given
    if shutil.which("uv"):
        run(["uv", "python", "install", "3.11"])
        found = subprocess.run(["uv", "python", "find", "3.11"], capture_output=True, text=True)
        if found.returncode == 0 and found.stdout.strip():
            return found.stdout.strip()
    if shutil.which("python3.11"):
        return "python3.11"
    raise KleanError("no Python 3.11: install uv (curl -LsSf https://astral.sh/uv/install.sh | sh) "
                     "and rerun, or give --python /path/to/python3.11")


def cmd_install_python(args) -> None:
    target = Path(args.dir).expanduser().resolve()
    run([base_python311(args.python), "-m", "venv", str(target)])
    py = str(venv_python(str(target)))
    run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "-q", *PYTHON_PACKAGES, *args.package])
    dll = find_python_dll(py)
    print(f"Python env: {target}\nlibpython: {dll}")
    try:
        ws = Workspace.load(Path.cwd())
        ws.python_venv, ws.python_dll = str(target), dll
        ws.save()
        print(f"saved in {ws.root / 'klean.json'}")
    except KleanError:
        print(f"Use it with: klean init --lean <LEAN> --python-venv {target}")


def cmd_init(args) -> None:
    root = Path(args.dir).expanduser().resolve()
    lean = Path(args.lean).expanduser().resolve()
    if not (lean / "Data" / "market-hours").is_dir():
        raise KleanError(f"{lean} doesn't look like a LEAN clone (no Data/market-hours)")
    root.mkdir(parents=True, exist_ok=True)
    ws = Workspace(root=root, lean_root=str(lean))
    if args.python_venv:
        ws.python_venv = str(Path(args.python_venv).expanduser().resolve())
        ws.python_dll = find_python_dll(str(venv_python(ws.python_venv)))
    ws.data.mkdir(exist_ok=True)
    if args.sample_data:
        # LEAN's sample market data (third-party vendors' prices; keep it local, don't redistribute)
        shutil.copytree(lean / "Data", ws.data, dirs_exist_ok=True)
    else:
        for name in LEAN_CONFIG_DIRS:
            shutil.copytree(lean / "Data" / name, ws.data / name, dirs_exist_ok=True)
        for rel in LEAN_OPTIONAL_FILES:
            if (lean / "Data" / rel).exists():
                (ws.data / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(lean / "Data" / rel, ws.data / rel)
    ws.save()
    print(f"workspace {root}: klean.json, data/ ({'LEAN Data incl. sample data' if args.sample_data else 'LEAN config files'})")
    if args.data_zip:
        install_data(ws, zip_path=Path(args.data_zip))
    else:
        print("Next: klean data install lean.zip")


def install_data(ws: Workspace, zip_path: Path | None = None, root: Path | None = None) -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))   # krx_lean from the clone; it needn't be installed
    from krx_lean import lean_install
    if zip_path:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            # lean-package writes data/equity/krx/...; also accept a zip without the data/ prefix
            target = ws.root if any(n.startswith("data/") for n in names) else ws.data
            base = target.resolve()
            for n in names:      # nothing outside the workspace, whatever the zip says
                dest = (base / n).resolve()
                if Path(n).is_absolute() or (dest != base and base not in dest.parents):
                    raise KleanError(f"{zip_path}: entry {n!r} would be written outside {base}; not unzipped")
            z.extractall(target)
        print(f"unzipped {len(names)} files from {zip_path} into {ws.data}")
        lean_install.install(ws.root, ws.data, config_only=True)
    else:
        lean_install.install(root, ws.data)
        ws.data_root = str(root.resolve())       # `klean update` uses it
        ws.save()


def cmd_data_install(args) -> None:
    ws = Workspace.load(Path.cwd())
    if sum(map(bool, (args.zip, args.root, args.demo))) != 1:
        raise KleanError("give one of: a lean.zip, --root <krx-lean data root>, or --demo (synthetic data)")
    if args.demo:
        install_demo(ws)
        return
    if results.is_demo_data(ws):
        raise KleanError(f"{ws.root} holds SYNTHETIC demo data; install real data into a new workspace "
                         "(klean init ~/krx-workspace ...) so the two never mix")
    install_data(ws, zip_path=Path(args.zip) if args.zip else None,
                 root=Path(args.root).expanduser() if args.root else None)


def install_demo(ws: Workspace) -> None:
    """Generate the synthetic demo data (krx_lean/demo.py), build it and install it."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import tempfile
    from krx_lean import build, demo, lean_install
    krx = ws.data / "equity" / "krx"
    if any((krx / "daily").glob("*.zip")) and not results.is_demo_data(ws):
        raise KleanError(f"{ws.root} already has real KRX data; put the synthetic demo data in its own "
                         "workspace (klean init ~/krx-demo ...)")
    holidays = set()
    mhdb = ws.data / "market-hours" / "market-hours-database.json"
    if mhdb.exists():   # LEAN's KRX holidays, so the demo calendar matches LEAN's
        entry = json.loads(mhdb.read_text(encoding="utf-8"))["entries"].get("Index-krx-[*]", {})
        for d in entry.get("holidays", []):
            m, day, y = d.split("/")
            holidays.add(f"{int(y):04d}{int(m):02d}{int(day):02d}")
    print(f"*** {results.DEMO_BANNER} ***")
    with tempfile.TemporaryDirectory(prefix="klean-demo-") as tmp:
        info = demo.generate(Path(tmp), holidays)
        build.build(Path(tmp))
        lean_install.install(Path(tmp), ws.data)
    print(f"synthetic demo data installed: {info['securities']} made-up securities (codes D…/E…), "
          f"{info['first']} → {info['last']}, KOSPI and KOSPI 200 indices.\n"
          "Every folder is marked SYNTHETIC-DEMO-DATA.txt; runs, reports and the GUI say so.")


def cmd_data_status(args) -> None:
    st = results.data_status(Workspace.load(Path.cwd()))
    if args.json:
        print(json.dumps(st, indent=2))
        return
    if st.get("synthetic_demo_data"):
        print(f"*** {results.DEMO_BANNER} ***")
    print(f"KRX data in {st['folder']}")
    print(f"  securities          {st['securities']}")
    if "last_date" in st:
        print(f"  dates               {st['first_date']} → {st['last_date']}")
        by_market = ", ".join(f"{k} {v}" for k, v in sorted(st["active_by_market"].items()))
        print(f"  active on last date {st['active']} ({by_market}); delisted/suspended {st['delisted_or_suspended']}")
    if "universe_files" in st:
        u = st["universe_files"]
        print(f"  universe files      {u['count']} ({u['first']} → {u['last']})")
    print(f"  factor files        {st['factor_files']}")
    for name, rng in st["indices"].items():
        print(f"  index {name:13} {rng['first']} → {rng['last']}")
    mh = st.get("market_hours", {})
    print(f"  Equity-krx hours    {'installed, ' + str(mh['holidays']) + ' holidays' if mh.get('installed') else 'MISSING: run klean data install'}")


def cmd_project_create(args) -> None:
    ws = Workspace.load(Path.cwd())
    project = projects.create(ws, args.name, args.language, args.template)
    print(f"created {project} ({args.language}, {args.template}). Run: klean backtest \"{args.name}\"")


def cmd_project_delete(args) -> int:
    ws = Workspace.load(Path.cwd())
    target = (ws.root / args.name).resolve()
    n = len(results.runs(target)) if target.is_dir() else 0
    if not args.yes:
        answer = input(f"Delete {target} and its {n} backtest(s)? Type the project name to confirm: ")
        if answer.strip() != args.name:
            print("not deleted")
            return 1
    print(f"deleted {projects.delete(ws, args.name)}")
    return 0


def cmd_optimize(args) -> int:
    from klean import optimize
    project = Path(args.project).expanduser()
    if project.exists():
        ws = Workspace.load(project)
    else:
        ws = Workspace.load(Path.cwd())
        project = ws.root / project
    if results.is_demo_data(ws) and not args.estimate:
        print(f"*** {results.DEMO_BANNER} ***")
    s = optimize.optimize(ws, project, [tuple(p) for p in args.parameter or []], target=args.target,
                          direction=args.target_direction, constraints=args.constraint,
                          max_concurrent=args.max_concurrent_backtests,
                          extra_config=dict(args.extra_config or []), name=args.name or "",
                          build_config=args.build_config, max_backtests=args.max_backtests, estimate=args.estimate,
                          timeout=args.timeout)
    if args.estimate:
        print(f"{s['backtests']} backtests, {s['concurrent']} at a time")
        return 0
    header, rows = optimize.ranking(s)
    print("\n" + results.format_table(header, rows))
    print(f"\n{len(s['runs'])} backtests in {s['seconds']} s -> {s['folder']}")
    if s["best"]:
        print(f"best ({s['direction']} {s['target']}): {Path(s['folder']) / s['best']}")
    else:
        print("no run met the constraints")
    if results.is_demo_data(ws):
        print(f"*** {results.DEMO_BANNER} ***")
    return 0


def cmd_report(args) -> int:
    from klean.report import report
    ws = Workspace.load(Path.cwd())
    if args.run:
        run_dir = results.resolve_run(ws, args.run)
    else:
        found = sorted((r for p in ws.root.iterdir() if p.is_dir() for r in results.runs(p)),
                       key=lambda r: r.name)
        if not found:
            raise KleanError("no backtests in this workspace yet")
        run_dir = found[-1]
    r = report(ws, run_dir, destination=Path(args.report_destination) if args.report_destination else None,
               strategy_name=args.strategy_name or "", strategy_version=args.strategy_version or "",
               strategy_description=args.strategy_description, overwrite=args.overwrite,
               css=Path(args.css) if args.css else None, html=Path(args.html) if args.html else None, pdf=args.pdf)
    print(f"report: {r['report']}" + (f"\npdf:    {r['pdf']}" if "pdf" in r else ""))
    return 0


def cmd_research(args) -> int:
    from klean import research
    project = Path(args.project).expanduser()
    if project.exists():
        ws = Workspace.load(project)
    else:
        ws = Workspace.load(Path.cwd())
        project = ws.root / project
    if not project.is_dir():
        raise KleanError(f"no project {project}: create it with `klean project-create`")
    project = project.resolve()
    if args.execute:
        out = research.execute(ws, project, args.execute, timeout=args.timeout)
        print(f"executed: {out}")
        return 0
    return research.launch(ws, project, port=args.port, open_browser=not args.no_browser)


def cmd_logs(args) -> None:
    ws = Workspace.load(Path.cwd())
    run_dir = results.resolve_run(ws, args.run)
    lines = results.log_text(run_dir, console=args.console).splitlines()
    if args.tail:
        lines = lines[-args.tail:]
    print(f"# {run_dir}")
    print("\n".join(lines))
    error = results.run_error(run_dir)
    if error:
        print(f"\n# this run FAILED: {error.splitlines()[0]}\n# full output: klean logs {args.run} --console")
    elif not lines and not args.console:
        print("# the algorithm logged nothing; LEAN's output: --console")


def cmd_compare(args) -> int:
    ws = Workspace.load(Path.cwd())
    run_dirs = [results.resolve_run(ws, r) for r in args.runs]
    if len(run_dirs) < 2:
        raise KleanError("give at least two runs")
    header, rows, verdict = results.compare(run_dirs, all_keys=args.all)
    if any(results.run_is_demo(r) for r in run_dirs):
        print(f"*** {results.DEMO_BANNER} ***")
    for r in run_dirs:
        if results.run_error(r):
            print(f"note: {results.label(r)} FAILED: {results.run_error(r).splitlines()[0]}")
    print(results.format_table(header, rows))
    curves = verdict["equity_curves_identical"]
    print(f"\nequity curves: {'identical' if curves else 'different' if curves is False else 'not available'}")
    print("IDENTICAL" if verdict["identical"] else f"DIFFERENT: {', '.join(verdict['differing']) or 'equity curve'}")
    return 0


def cmd_config(args) -> int:
    ws = Workspace.load(Path.cwd())
    key = getattr(args, "key", None)
    if args.config_cmd == "list":
        for k in WORKSPACE_KEYS:
            print(f"{k} = {getattr(ws, k)}")
        for k, v in sorted(ws.lean_config.items()):
            print(f"{k} = {v}    (LEAN config)")
        return 0
    if args.config_cmd == "get":
        if key in WORKSPACE_KEYS:
            print(getattr(ws, key))
        elif key in ws.lean_config:
            print(ws.lean_config[key])
        else:
            raise KleanError(f"{key} isn't set")
        return 0
    if args.config_cmd == "set":
        if key == "python_venv":
            ws.python_venv = str(Path(args.value).expanduser().resolve())
            ws.python_dll = find_python_dll(str(venv_python(ws.python_venv)))
        elif key == "lean_root":
            lean = Path(args.value).expanduser().resolve()
            if not (lean / "Data" / "market-hours").is_dir():
                raise KleanError(f"{lean} doesn't look like a LEAN clone")
            ws.lean_root = str(lean)
        elif key in WORKSPACE_KEYS:
            setattr(ws, key, args.value)
        else:
            ws.lean_config[key] = args.value   # passed to LEAN on every backtest
    else:  # unset
        if key in WORKSPACE_KEYS:
            if key == "lean_root":
                raise KleanError("lean_root can't be unset")
            setattr(ws, key, "")
        elif ws.lean_config.pop(key, None) is None:
            raise KleanError(f"{key} isn't set")
    ws.save()
    return 0


def cmd_lean(args) -> int:
    ws = Workspace.load(Path.cwd())
    lean = Path(ws.lean_root)
    commit = git_commit(lean)
    if args.lean_cmd == "status":
        built = (ws.launcher_dir / "QuantConnect.Lean.Launcher.dll").exists()
        print(f"LEAN {lean}\n  commit {commit or 'unknown'}{'' if commit.startswith(LEAN_COMMIT) else '  (tested: ' + LEAN_COMMIT[:7] + ')'}"
              f"\n  build  {'present' if built else 'MISSING'}")
        return 0
    checkout_and_build_lean(lean, args.commit)
    print(f"LEAN {lean} updated: {commit[:12] or '?'} -> {git_commit(lean)[:12]}")
    if not args.commit.startswith(LEAN_COMMIT):
        print("This isn't the commit krx-lean was tested with: rerun your reference backtests and "
              "`klean compare` them with earlier runs before relying on it.")
    return 0


def cmd_backtest(args) -> int:
    project = Path(args.project).expanduser()
    if project.exists():
        ws = Workspace.load(project)       # the workspace the project lives in
    else:
        ws = Workspace.load(Path.cwd())
        project = ws.root / project
    demo = results.is_demo_data(ws)
    if demo:
        print(f"*** {results.DEMO_BANNER} ***", flush=True)
    if project.is_dir() and projects.models_state(project) == "differs":
        copy, _ = projects.models_copy(project)
        print(f"note: {project.name}/{copy.name} differs from krx-lean's current KRX models (older tax/tick "
              f"rules, or your own edits). `klean models update {project.name}` replaces it.", flush=True)
    result = backtest(ws, project, dict(args.parameter or []), extra_config=dict(args.extra_config or []),
                      output=Path(args.output) if args.output else None, backtest_name=args.backtest_name or "",
                      build_config=args.build_config, timeout=args.timeout)
    print(f"\nresults: {result['results']}")
    for k, v in result["statistics"].items():
        print(f"  {k:28} {v}")
    note = slippage_note(project, dict(args.parameter or []))
    if note:
        print(note)
    if result.get("gil_abort_at_exit"):
        print("(LEAN's Python bridge printed a 'GIL must always be released' error while shutting down, after "
              "the results were written: the run is complete.)")
    if demo:
        print(f"*** {results.DEMO_BANNER} ***")
    return 0


def slippage_note(project: Path, parameters: dict[str, str]) -> str:
    """One line saying whether the run used slippage, for strategies that read the
    ``slippage_ticks`` parameter (the templates and the example do)."""
    main = next((f for f in (project / "main.py", project / "Main.cs") if f.exists()), None)
    if main is None or "slippage_ticks" not in main.read_text(encoding="utf-8", errors="replace"):
        return ""
    try:
        ticks = int(parameters.get("slippage_ticks", "0"))
    except ValueError:
        return ""
    if ticks > 0:
        return f"slippage: {ticks} KRX tick{'s' if ticks > 1 else ''} per share on every fill"
    return (f"slippage: off (orders fill at the bar's price). Switch it on with "
            f"`klean backtest {project.name} --parameter slippage_ticks 1`")


def cmd_gui(args) -> int:
    from klean import gui
    gui.serve(Workspace.load(Path.cwd()), port=args.port, open_browser=not args.no_browser)
    return 0


def load_env_file(path: Path) -> list[str]:
    """Set KEY=VALUE lines of ``path`` as environment variables unless they are already set.
    Returns the names set (never the values)."""
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value and not os.environ.get(key):
            os.environ[key] = value
            names.append(key)
    return names


def cmd_update(args) -> int:
    """The daily routine in one command: `krx-lean --root R all`, then `klean data install --root R`."""
    ws = Workspace.load(Path.cwd())
    if results.is_demo_data(ws):
        raise KleanError(f"{ws.root} holds SYNTHETIC demo data: nothing to update (real data goes in its own workspace)")
    root = Path(args.root).expanduser() if args.root else Path(ws.data_root) if ws.data_root else None
    if root is None:
        raise KleanError("no data root known for this workspace: `klean update --root ~/krx-data` "
                         "(remembered afterwards)")
    env_file = Path(args.env_file).expanduser()
    if env_file.is_file():
        names = load_env_file(env_file)
        if names:
            print(f"klean: {', '.join(names)} from {env_file}")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from krx_lean import cli as pipeline
    print(f"klean: krx-lean --root {root} all", flush=True)
    try:
        code = pipeline.main(["--root", str(root), "all"])
    except SystemExit as e:        # e.g. "KRX_API_KEY is not set"
        raise KleanError(f"{e} (export it, or put KRX_API_KEY=... in {env_file})") from None
    if not (root / "lean" / "equity" / "krx").is_dir():
        raise KleanError(f"nothing built in {root} (see the messages above)")
    install_data(ws, root=root)
    st = results.data_status(ws)
    print(f"klean: workspace data now {st.get('first_date', '?')} → {st.get('last_date', '?')}, "
          f"{st['securities']} securities" + ("" if code == 0 else
          "  (the download stopped early: run `klean update` again to continue)"))
    return code


def cmd_models(args) -> int:
    ws = Workspace.load(Path.cwd())
    if args.models_cmd == "status":
        rows = [[p.name, projects.language_of(p), projects.models_copy(p)[0].name, projects.models_state(p)]
                for p in projects.list_projects(ws)]
        print(results.format_table(["project", "language", "file", "KRX models"], rows) if rows else "no projects")
        if any(r[3] == "differs" for r in rows):
            print("\n'differs': krx-lean's models changed after the project was created (tax rates, tick sizes, "
                  "fixes), or you edited the copy.\n`klean models update NAME` replaces it and keeps yours as *.bak.")
        return 0
    names = [p.name for p in projects.list_projects(ws)] if args.all else args.names
    if not names:
        raise KleanError("give project names, or --all")
    for name in names:
        project = ws.root / name
        projects.language_of(project)
        before = projects.models_state(project)
        backup = projects.update_models(project)
        copy = projects.models_copy(project)[0]
        print(f"{name}: {copy.name} " + ("already current" if before == "current" else
              "updated" + (f" (previous copy kept as {backup.name})" if backup else "")))
    return 0


def cmd_doctor(args) -> int:
    try:
        ws = Workspace.load(Path.cwd())
    except KleanError:
        ws = None
    rows = check(ws)
    if ws is not None:
        rows.append(projects.models_row(ws))
    for item, ok, detail in rows:
        print(f"  {'OK ' if ok else 'NO '} {item:32} {detail}")
    return 0 if all(ok for item, ok, _ in rows if not item.startswith("Python env")) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="klean", description="Local LEAN workflow for KRX data on a LEAN source "
                                "build: no Docker, no QuantConnect account.",
                                epilog=__doc__.split("\n\n", 1)[1] if __doc__ else None,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"klean {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("install-lean", help="clone LEAN at the tested commit and build it (needs git, .NET 10)")
    s.add_argument("--dir", default="~/Lean")
    s.add_argument("--commit", default=LEAN_COMMIT)
    s.set_defaults(func=cmd_install_lean)

    s = sub.add_parser("install-python", help="create a Python 3.11 environment with pandas/numpy for LEAN")
    s.add_argument("--dir", default="~/.klean/py311")
    s.add_argument("--python", help="a CPython 3.11 with a shared libpython (default: uv's 3.11, else python3.11)")
    s.add_argument("--package", action="append", default=[], help="extra pip package (repeatable)")
    s.set_defaults(func=cmd_install_python)

    s = sub.add_parser("init", help="create a workspace (klean.json + data/)")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--lean", required=True, help="the LEAN clone built with `klean install-lean`")
    s.add_argument("--python-venv", help="Python 3.11 env (from `klean install-python`) for Python projects")
    s.add_argument("--data-zip", help="also install this lean.zip")
    s.add_argument("--sample-data", action="store_true", help="also copy LEAN's sample data (US equities etc.)")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("data", help="KRX data")
    dsub = s.add_subparsers(dest="data_cmd", required=True)
    d = dsub.add_parser("install", help="unzip lean.zip into data/ (or copy from a krx-lean data root) + KRX config")
    d.add_argument("zip", nargs="?")
    d.add_argument("--root", help="krx-lean data root with lean/ (instead of a zip)")
    d.add_argument("--demo", action="store_true",
                   help="SYNTHETIC demo data (made-up prices) to try klean without API keys; use its own workspace")
    d.set_defaults(func=cmd_data_install)
    d = dsub.add_parser("status", help="KRX data range, securities, universe files, indices, market hours")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_data_status)

    s = sub.add_parser("project-create", help="create a project with the KRX models")
    s.add_argument("name")
    s.add_argument("--language", choices=["python", "csharp"], default="python")
    s.add_argument("--template", choices=projects.TEMPLATES, default="buy-hold",
                   help="buy-hold (default), top-market-cap (the example strategy) or empty")
    s.set_defaults(func=cmd_project_create)

    s = sub.add_parser("project-delete", help="delete a project folder and its backtests")
    s.add_argument("name")
    s.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    s.set_defaults(func=cmd_project_delete)

    s = sub.add_parser("backtest", help="run a backtest; results in <project>/backtests/<timestamp>/")
    s.add_argument("project")
    s.add_argument("--parameter", nargs=2, action="append", metavar=("KEY", "VALUE"),
                   help="algorithm parameter (get_parameter / GetParameter), repeatable")
    s.add_argument("--extra-config", nargs=2, action="append", metavar=("KEY", "VALUE"),
                   help="LEAN config key for this run (on top of `klean config`), repeatable")
    s.add_argument("--backtest-name", help="name for the run (results folder suffix)")
    s.add_argument("--output", help="results folder (default: <project>/backtests/<timestamp>[_<name>])")
    s.add_argument("--build-config", choices=["Release", "Debug"], default="Release", help="C# build configuration")
    s.add_argument("--timeout", type=float, default=0, metavar="SECONDS",
                   help="stop LEAN if the backtest runs longer (default: no limit)")
    s.set_defaults(func=cmd_backtest)

    s = sub.add_parser("optimize", help="grid search over parameters; results in <project>/optimizations/<timestamp>/")
    s.add_argument("project")
    s.add_argument("--parameter", nargs=4, action="append", metavar=("NAME", "MIN", "MAX", "STEP"),
                   help="parameter range, inclusive (repeatable); read it with get_parameter / GetParameter")
    s.add_argument("--target", default="Sharpe Ratio", help="statistic to optimize (default: Sharpe Ratio)")
    s.add_argument("--target-direction", choices=["max", "min"], default="max")
    s.add_argument("--constraint", action="append",
                   help="'STATISTIC OP VALUE', values as shown in the statistics (25 for 25%%), repeatable")
    s.add_argument("--max-concurrent-backtests", type=int, default=0, help="default: half the CPU cores")
    s.add_argument("--max-backtests", type=int, default=500, help="refuse larger grids (default: 500)")
    s.add_argument("--estimate", action="store_true", help="only count the backtests")
    s.add_argument("--extra-config", nargs=2, action="append", metavar=("KEY", "VALUE"))
    s.add_argument("--name", help="name for the optimization (folder suffix)")
    s.add_argument("--build-config", choices=["Release", "Debug"], default="Release")
    s.add_argument("--timeout", type=float, default=0, metavar="SECONDS",
                   help="stop each backtest that runs longer; it counts as a failed run (default: no limit)")
    s.set_defaults(func=cmd_optimize)

    s = sub.add_parser("report", help="LEAN's HTML report for a run (default: the workspace's latest run)")
    s.add_argument("run", nargs="?", help="project (its latest run), PROJECT/RUN or a results folder")
    s.add_argument("--report-destination", help="default: <run>/report.html")
    s.add_argument("--strategy-name", help="default: the project name")
    s.add_argument("--strategy-version")
    s.add_argument("--strategy-description", help="default: algorithm, parameters, run, data date, LEAN commit")
    s.add_argument("--overwrite", action="store_true", help="replace an existing report")
    s.add_argument("--css", help="CSS file overriding the report's styles")
    s.add_argument("--html", help="custom HTML template (LEAN's Report/template.html format)")
    s.add_argument("--pdf", action="store_true", help="also write a PDF (wkhtmltopdf or Chromium on the PATH)")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("research", help="JupyterLab with LEAN's QuantBook on the workspace's data (project's research.ipynb)")
    s.add_argument("project")
    s.add_argument("--port", type=int, default=0, help="port (default: a free one)")
    s.add_argument("--no-browser", action="store_true", help="don't open the browser")
    s.add_argument("--execute", metavar="NOTEBOOK", nargs="?", const="research.ipynb",
                   help="run the notebook without a browser; writes NOTEBOOK.executed.ipynb")
    s.add_argument("--timeout", type=int, default=600, help="seconds per cell with --execute")
    s.set_defaults(func=cmd_research)

    s = sub.add_parser("logs", help="show a run's algorithm log (default: the project's latest run)")
    s.add_argument("run", help="project, PROJECT/RUN (name or prefix) or a results folder")
    s.add_argument("--console", action="store_true", help="LEAN's full console output instead")
    s.add_argument("--tail", type=int, default=0, help="only the last N lines")
    s.set_defaults(func=cmd_logs)

    s = sub.add_parser("compare", help="compare runs: statistics and equity curves")
    s.add_argument("runs", nargs="+", help="projects (latest run), PROJECT/RUN or results folders")
    s.add_argument("--all", action="store_true", help="all statistics, not just the main ones")
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("config", help="workspace settings (klean.json); other keys are LEAN config for every run")
    csub = s.add_subparsers(dest="config_cmd", required=True)
    csub.add_parser("list").set_defaults(func=cmd_config)
    c = csub.add_parser("get")
    c.add_argument("key")
    c.set_defaults(func=cmd_config)
    c = csub.add_parser("set")
    c.add_argument("key")
    c.add_argument("value")
    c.set_defaults(func=cmd_config)
    c = csub.add_parser("unset")
    c.add_argument("key")
    c.set_defaults(func=cmd_config)

    s = sub.add_parser("lean", help="the LEAN build used by this workspace")
    lsub = s.add_subparsers(dest="lean_cmd", required=True)
    lsub.add_parser("status", help="commit and build state").set_defaults(func=cmd_lean)
    u = lsub.add_parser("update", help="check out another LEAN commit and rebuild")
    u.add_argument("--commit", default=LEAN_COMMIT, help="default: the commit krx-lean was tested with")
    u.set_defaults(func=cmd_lean)

    s = sub.add_parser("update", help="download new KRX days, rebuild, and install into this workspace")
    s.add_argument("--root", help="krx-lean data root (default: the one last installed here)")
    s.add_argument("--env-file", default="~/.config/krx-lean.env",
                   help="file with KRX_API_KEY=... / DATA_GO_KR_KEY=... lines, used for keys not already "
                        "in the environment (default: ~/.config/krx-lean.env)")
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("models", help="the projects' copies of the KRX models (krx_models.py / KrxModels.cs)")
    msub = s.add_subparsers(dest="models_cmd", required=True)
    msub.add_parser("status", help="which projects have krx-lean's current models").set_defaults(func=cmd_models)
    m = msub.add_parser("update", help="replace a project's copy with the current models (old copy kept as .bak)")
    m.add_argument("names", nargs="*")
    m.add_argument("--all", action="store_true")
    m.set_defaults(func=cmd_models)

    s = sub.add_parser("doctor", help="check dotnet, the LEAN build, data and the Python env")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("gui", help="local web page (127.0.0.1 only): projects, runs, charts, compare, start backtests")
    s.add_argument("--port", type=int, default=0, help="port (default: a free one)")
    s.add_argument("--no-browser", action="store_true", help="don't open the browser")
    s.set_defaults(func=cmd_gui)

    args = p.parse_args(argv)
    try:
        return args.func(args) or 0
    except KleanError as e:
        print(f"klean: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
