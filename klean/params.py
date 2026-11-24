"""The parameters a strategy reads, found in its code: ``get_parameter("x", default)`` /
``GetParameter("x", default)`` calls, and ``set_period`` / ``KrxModels.SetPeriod`` (the
``start_date`` / ``end_date`` parameters). For the GUI's New backtest and New optimization forms.

Python is read with ``ast`` (defaults such as ``str(self.HOLDINGS)`` resolve through class and
module constants); C# with patterns (literals, or a field / constant initialised with one). The
KRX models file (krx_models.py / KrxModels.cs) is left out: its calls belong to every strategy.
A default that can't be worked out is "" (the parameter is still listed).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from klean import projects, results

MODELS = {"krx_models.py", "KrxModels.cs"}
GETTERS = {"get_parameter", "GetParameter"}
PERIOD = {"set_period", "SetPeriod"}


def kind_of(value: str) -> str:
    """"int", "float", "date" (YYYY-MM-DD) or "text". Digits with a leading zero ("005930")
    are a code, not a number."""
    if re.fullmatch(r"-?0\d+", value):
        return "text"
    if re.fullmatch(r"-?\d+", value):
        return "int"
    if re.fullmatch(r"-?(\d+\.\d*|\.\d+)([eE]-?\d+)?|-?\d+[eE]-?\d+", value):
        return "float"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return "date"
    return "text"


def _entry(name: str, default: str, path: Path, project: Path, line: int, kind: str = "") -> dict:
    return {"name": name, "default": default, "kind": kind or (kind_of(default) if default else "text"),
            "where": f"{path.relative_to(project).as_posix()}:{line}"}


# ---------------------------------------------------------------- Python

def _constants(tree: ast.AST) -> dict[str, ast.AST]:
    """NAME = <literal> at module level and in class bodies (later ones win)."""
    out: dict[str, ast.AST] = {}
    bodies = [tree.body] + [n.body for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    for body in bodies:
        for node in body:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) and node.value else []
            for t in targets:
                if isinstance(t, ast.Name) and node.value is not None:
                    out[t.id] = node.value
    return out


def _literal(node: ast.AST | None, consts: dict[str, ast.AST], depth: int = 0) -> str | None:
    """The value of a default as text, if it can be worked out."""
    if node is None or depth > 5:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float)) and not isinstance(node.value, bool):
        return str(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _literal(node.operand, consts, depth + 1)
        return f"-{inner}" if inner is not None and kind_of(inner) in ("int", "float") else None
    if isinstance(node, ast.Name) and node.id in consts:
        return _literal(consts[node.id], consts, depth + 1)
    if isinstance(node, ast.Attribute) and node.attr in consts:            # self.HOLDINGS, Algo.HOLDINGS
        return _literal(consts[node.attr], consts, depth + 1)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("str", "int", "float") \
            and len(node.args) == 1:
        inner = _literal(node.args[0], consts, depth + 1)
        if inner is None:
            return None
        try:
            return {"str": str, "int": lambda v: str(int(float(v))), "float": lambda v: str(float(v))}[node.func.id](inner)
        except ValueError:
            return None
    return None


def _name(func: ast.AST) -> str:
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""


def python_parameters(path: Path, project: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return []
    consts = _constants(tree)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _name(node.func)
        if name in GETTERS and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            default_node = node.args[1] if len(node.args) > 1 else next(
                (k.value for k in node.keywords if k.arg in ("default_value", "default")), None)
            default = _literal(default_node, consts) or ""
            wrapper = parents.get(node)                 # int(self.get_parameter(...)) -> int
            kind = _name(wrapper.func) if isinstance(wrapper, ast.Call) and _name(wrapper.func) in ("int", "float") else ""
            found.append((node.lineno, _entry(node.args[0].value, default, path, project, node.lineno, kind)))
        elif name in PERIOD:
            args = node.args[1:] if node.args else []      # set_period(self, start, end=None)
            start = _literal(args[0], consts) if args else None
            end = _literal(args[1], consts) if len(args) > 1 else None
            found.append((node.lineno, _entry("start_date", start or "", path, project, node.lineno, "date")))
            found.append((node.lineno, _entry("end_date", end or "", path, project, node.lineno, "date")))
    return [e for _, e in sorted(found, key=lambda x: x[0])]


# ---------------------------------------------------------------- C#

CS_GET = re.compile(r'\bGetParameter\s*\(\s*"((?:[^"\\]|\\.)+)"\s*(?:,\s*([^,()]+?|\w+\([^()]*\)))?\s*\)')
CS_PERIOD = re.compile(r'\bSetPeriod\s*\(\s*this\s*,\s*"([^"]*)"(?:\s*,\s*"([^"]*)")?')
CS_LITERAL = re.compile(r'^(-?\d+(?:\.\d+)?)[mMdDfFlL]?$|^"((?:[^"\\]|\\.)*)"$')


def _cs_literal(text: str, source: str) -> str | None:
    text = text.strip()
    m = CS_LITERAL.match(text)
    if m:
        return m.group(1) if m.group(1) is not None else m.group(2)
    if re.fullmatch(r"[A-Za-z_]\w*", text):                 # a constant or field: Holdings = 20;
        m = re.search(rf"\b{text}\s*=\s*(-?\d+(?:\.\d+)?[mMdDfFlL]?|\"(?:[^\"\\]|\\.)*\")\s*;", source)
        if m:
            return _cs_literal(m.group(1), "")
    return None


def csharp_parameters(path: Path, project: Path) -> list[dict]:
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    code = re.sub(r"//[^\n]*", lambda m: " " * len(m.group(0)), source)       # comments out, offsets kept
    line = lambda pos: code.count("\n", 0, pos) + 1               # noqa: E731
    found = []
    for m in CS_GET.finditer(code):
        default = _cs_literal(m.group(2), code) if m.group(2) else None
        found.append((m.start(), _entry(m.group(1), default or "", path, project, line(m.start()))))
    for m in CS_PERIOD.finditer(code):
        found.append((m.start(), _entry("start_date", m.group(1) or "", path, project, line(m.start()), "date")))
        found.append((m.start(), _entry("end_date", m.group(2) or "", path, project, line(m.start()), "date")))
    return [e for _, e in sorted(found, key=lambda x: x[0])]


# ---------------------------------------------------------------- a project

def find(project: Path) -> list[dict]:
    """Every parameter the project's strategy reads, the strategy file's first, each name once
    (its first place)."""
    main = projects.main_file(project)
    files = sorted((f for f in results.source_files(project) if f.name not in MODELS and f.suffix in (".py", ".cs")),
                   key=lambda f: (f != main, f.as_posix()))
    seen: dict[str, dict] = {}
    for f in files:
        for e in (python_parameters if f.suffix == ".py" else csharp_parameters)(f, project):
            if e["name"] not in seen:
                seen[e["name"]] = e
            elif not seen[e["name"]]["default"] and e["default"]:
                seen[e["name"]]["default"] = e["default"]
    return list(seen.values())
