"""The `klean <verb> <noun>` commands, the 0.0.9 names kept as hidden aliases, and `update all`."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]

from klean import cli
from klean.workspace import LEAN_COMMIT, KleanError, Workspace


def dispatched(argv):
    """The cmd_* function `klean argv` runs and the args it gets (the function itself is mocked)."""
    calls = []
    names = [n for n in dir(cli) if n.startswith("cmd_")]
    with contextlib.ExitStack() as stack:
        for n in names:
            stack.enter_context(mock.patch.object(cli, n, side_effect=lambda a, n=n: calls.append((n, a)) or 0))
        cli.main(argv)
    assert len(calls) == 1, calls
    return calls[0]


class CommandsTest(unittest.TestCase):
    def check(self, argv, func, **attrs):
        name, args = dispatched(argv)
        self.assertEqual(name, func, argv)
        for k, v in attrs.items():
            self.assertEqual(getattr(args, k), v, (argv, k))

    def test_verb_noun(self):
        self.check(["install", "lean", "--dir", "/x"], "cmd_install_lean", dir="/x", commit=LEAN_COMMIT)
        self.check(["install", "python", "--package", "scipy"], "cmd_install_python", package=["scipy"])
        self.check(["install", "data", "--demo"], "cmd_data_install", demo=True, zip=None)
        self.check(["install", "data", "lean.zip"], "cmd_data_install", zip="lean.zip")
        self.check(["update", "data", "--root", "/r"], "cmd_update", root="/r")
        self.check(["update", "lean", "--commit", "abc"], "cmd_lean", lean_cmd="update", commit="abc")
        self.check(["update", "lean"], "cmd_lean", lean_cmd="update", commit=LEAN_COMMIT)
        self.check(["update", "models", "--all"], "cmd_models", models_cmd="update", all=True)
        self.check(["update", "models", "A", "B"], "cmd_models", names=["A", "B"])
        self.check(["update", "klean"], "cmd_update_klean")
        self.check(["update", "all", "--root", "/r"], "cmd_update_all", root="/r", after_pull=False)
        self.check(["status", "data", "--json"], "cmd_data_status", json=True)
        self.check(["status", "lean"], "cmd_lean", lean_cmd="status")
        self.check(["status", "models"], "cmd_models", models_cmd="status")
        self.check(["status", "all"], "cmd_status_all")
        self.check(["create-project", "P", "--language", "csharp"], "cmd_project_create", name="P",
                   language="csharp", template="buy-hold")
        self.check(["delete-project", "P", "--yes"], "cmd_project_delete", name="P", yes=True)

    def test_old_names_still_work(self):
        self.check(["install-lean"], "cmd_install_lean", dir="~/Lean")
        self.check(["install-python"], "cmd_install_python")
        self.check(["data", "install", "--root", "/r"], "cmd_data_install", root="/r")
        self.check(["data", "status"], "cmd_data_status", json=False)
        self.check(["project-create", "P", "--template", "empty"], "cmd_project_create", template="empty")
        self.check(["project-delete", "P"], "cmd_project_delete", yes=False)
        self.check(["lean", "status"], "cmd_lean", lean_cmd="status")
        self.check(["lean", "update", "--commit", "abc"], "cmd_lean", lean_cmd="update", commit="abc")
        self.check(["models", "status"], "cmd_models", models_cmd="status")
        self.check(["models", "update", "--all"], "cmd_models", models_cmd="update", all=True)
        self.check(["update"], "cmd_update", root=None, env_file="~/.config/krx-lean.env")
        self.check(["update", "--root", "/r"], "cmd_update", root="/r")
        self.check(["create", "project", "P"], "cmd_project_create", name="P")       # 0.0.10
        self.check(["delete", "project", "P", "--yes"], "cmd_project_delete", yes=True)

    def test_help_lists_only_the_new_names(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit):
            cli.main(["--help"])
        text = out.getvalue()
        listed = text.split("positional arguments:")[1].split("options:")[0]
        for new in ("install", "update", "status", "create-project", "delete-project", "backtest"):
            self.assertIn(f"    {new} ", listed)
        commands = [line.split()[0] for line in listed.splitlines() if line.startswith("    ") and line[4] != " "]
        self.assertEqual(commands, ["install", "init", "update", "status", "create-project", "delete-project", "backtest", "optimize",
                                    "report", "research", "logs", "compare", "config", "doctor", "gui"])
        self.assertIn("klean update all", text)

    def test_noun_required(self):
        for verb in ("install", "status"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
                cli.main([verb])
            self.assertEqual(e.exception.code, 2, verb)


class UpdateAllTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.ws = Workspace(root=root / "ws", lean_root=str(root / "Lean"))
        self.ws.data.mkdir(parents=True)
        self.ws.save()
        self.cwd = os.getcwd()
        os.chdir(self.ws.root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_all(self, argv, commit, demo=False):
        calls = []
        with mock.patch.object(cli, "git_commit", return_value=commit), \
             mock.patch.object(cli, "cmd_lean", side_effect=lambda a: calls.append(("lean", a.lean_cmd, a.commit))), \
             mock.patch.object(cli, "cmd_update", side_effect=lambda a: calls.append(("data", a.root)) or 0), \
             mock.patch.object(cli, "cmd_models", side_effect=lambda a: calls.append(("models", a.models_cmd))), \
             mock.patch.object(cli.results, "is_demo_data", return_value=demo), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            code = cli.main(argv)
        return code, calls, out.getvalue()

    def test_after_pull_rebuilds_lean_only_when_needed(self):
        (self.ws.launcher_dir).mkdir(parents=True)
        (self.ws.launcher_dir / "QuantConnect.Lean.Launcher.dll").write_text("")
        code, calls, out = self.run_all(["update", "all", "--after-pull", "--root", "/r"], LEAN_COMMIT)
        self.assertEqual(code, 0)
        self.assertEqual(calls, [("data", "/r"), ("models", "status")])
        self.assertIn("already at the tested commit", out)
        _, calls, _ = self.run_all(["update", "all", "--after-pull", "--root", "/r"], "0123456")
        self.assertEqual(calls, [("lean", "update", LEAN_COMMIT), ("data", "/r"), ("models", "status")])

    def test_after_pull_skips_data_it_cannot_update(self):
        _, calls, out = self.run_all(["update", "all", "--after-pull"], "0123456", demo=True)
        self.assertEqual([c[0] for c in calls], ["lean", "models"])
        self.assertIn("SYNTHETIC demo data: skipped", out)
        _, calls, out = self.run_all(["update", "all", "--after-pull"], "0123456")
        self.assertEqual([c[0] for c in calls], ["lean", "models"])
        self.assertIn("no data root known", out)

    def test_pulls_then_continues_in_a_new_process(self):
        with mock.patch.object(cli, "cmd_update_klean") as pull, \
             mock.patch.object(cli.subprocess, "run", return_value=mock.Mock(returncode=3)) as sub, \
             contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["update", "all", "--root", "/r"])
        self.assertEqual(code, 3)
        pull.assert_called_once()
        cmd = sub.call_args[0][0]
        self.assertEqual(cmd[1:6], ["-m", "klean", "update", "all", "--after-pull"])
        self.assertEqual(cmd[-2:], ["--root", "/r"])

    def test_update_klean_needs_a_git_clone(self):
        with mock.patch.object(cli, "REPO_ROOT", Path(self.tmp.name)):
            with self.assertRaisesRegex(KleanError, "isn't running from a git clone"):
                cli.cmd_update_klean(None)


if __name__ == "__main__":
    unittest.main()
