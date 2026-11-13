"""`klean create-project`: a Python or C# project folder in the LEAN CLI's layout, with the KRX
models next to the algorithm."""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

from klean.workspace import REPO_ROOT, KleanError, Workspace

PY_MODELS = REPO_ROOT / "examples" / "python" / "krx_models.py"
CS_MODELS = REPO_ROOT / "examples" / "KrxModels.cs"
# Example strategies used as templates (copied as they are, class name included).
PY_TOP_MARKET_CAP = REPO_ROOT / "examples" / "python" / "krx_top_market_cap" / "main.py"
CS_TOP_MARKET_CAP = REPO_ROOT / "examples" / "KrxTopMarketCapAlgorithm.cs"
TEMPLATES = ("buy-hold", "top-market-cap", "empty")

PY_TEMPLATE = '''# region imports
from AlgorithmImports import *
from krx_models import KrxBoards, krx_benchmark, krx_initialize
# endregion


class {cls}(QCAlgorithm):
    """KRX strategy template (klean): buy and hold one stock with KRX fees and taxes.
    The stock is the parameter "code" (default {code}{code_note})."""

    def initialize(self):
        self.set_time_zone("Asia/Seoul")
        self.set_account_currency("KRW")
        self.set_start_date(2024, 1, 2)
        self.set_cash(100_000_000)
        boards = KrxBoards.load()
        slippage_ticks = int(self.get_parameter("slippage_ticks", "0"))   # KRX ticks lost per share on every fill
        self.set_security_initializer(lambda security: krx_initialize(security, boards, slippage_ticks=slippage_ticks))
        self.set_benchmark(krx_benchmark("kospi200"))
        code = self.get_parameter("code", "{code}")
        self.stock = self.add_equity(code, Resolution.DAILY, Market.KRX).symbol

    def on_data(self, data: Slice):
        if not self.portfolio.invested and data.contains_key(self.stock):
            self.set_holdings(self.stock, 0.9)
'''

PY_EMPTY = '''# region imports
from AlgorithmImports import *
from krx_models import KrxBoards, krx_benchmark, krx_initialize
# endregion


class {cls}(QCAlgorithm):
    """KRX strategy (klean, empty template): the required KRX settings, no trading yet."""

    def initialize(self):
        self.set_time_zone("Asia/Seoul")
        self.set_account_currency("KRW")
        self.set_start_date(2024, 1, 2)
        self.set_cash(100_000_000)
        boards = KrxBoards.load()
        slippage_ticks = int(self.get_parameter("slippage_ticks", "0"))   # KRX ticks lost per share on every fill
        self.set_security_initializer(lambda security: krx_initialize(security, boards, slippage_ticks=slippage_ticks))
        self.set_benchmark(krx_benchmark("kospi200"))

    def on_data(self, data: Slice):
        pass
'''

CS_EMPTY = '''using QuantConnect.Data;

namespace QuantConnect.Algorithm.CSharp
{{
    /// <summary>KRX strategy (klean, empty template): the required KRX settings, no trading yet.</summary>
    public class {cls} : QCAlgorithm
    {{
        public override void Initialize()
        {{
            SetTimeZone("Asia/Seoul");
            SetAccountCurrency("KRW");
            SetStartDate(2024, 1, 2);
            SetCash(100_000_000);
            var boards = KrxBoards.Load();
            var slippageTicks = GetParameter("slippage_ticks", 0);   // KRX ticks lost per share on every fill
            SetSecurityInitializer(security => KrxModels.Initialize(security, boards, slippageTicks: slippageTicks));
            SetBenchmark(KrxIndex.Benchmark("kospi200"));
        }}

        public override void OnData(Slice slice)
        {{
        }}
    }}
}}
'''

CS_TEMPLATE = '''using QuantConnect.Data;

namespace QuantConnect.Algorithm.CSharp
{{
    /// <summary>KRX strategy template (klean): buy and hold one stock with KRX fees and taxes.
    /// The stock is the parameter "code" (default {code}{code_note}).</summary>
    public class {cls} : QCAlgorithm
    {{
        private Symbol _stock;

        public override void Initialize()
        {{
            SetTimeZone("Asia/Seoul");
            SetAccountCurrency("KRW");
            SetStartDate(2024, 1, 2);
            SetCash(100_000_000);
            var boards = KrxBoards.Load();
            var slippageTicks = GetParameter("slippage_ticks", 0);   // KRX ticks lost per share on every fill
            SetSecurityInitializer(security => KrxModels.Initialize(security, boards, slippageTicks: slippageTicks));
            SetBenchmark(KrxIndex.Benchmark("kospi200"));
            var code = GetParameter("code", "{code}");
            _stock = AddEquity(code, Resolution.Daily, Market.KRX).Symbol;
        }}

        public override void OnData(Slice slice)
        {{
            if (!Portfolio.Invested && slice.ContainsKey(_stock)) SetHoldings(_stock, 0.9m);
        }}
    }}
}}
'''

# References the DLLs of the LEAN build named in klean.json; Private=false so nothing is copied
# (the launcher already has them loaded). Same target framework as LEAN at the tested commit.
CSPROJ_TEMPLATE = '''<Project Sdk="Microsoft.NET.Sdk">
  <!-- klean C# project: compiled against the LEAN build in klean.json (lean_root). -->
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <OutputType>Library</OutputType>
    <AppendTargetFrameworkToOutputPath>false</AppendTargetFrameworkToOutputPath>
    <Nullable>disable</Nullable>
    <ImplicitUsings>disable</ImplicitUsings>
    <NoWarn>CS0618;CS1591</NoWarn>
    <LeanBin Condition="'$(LeanBin)' == ''">{lean_bin}</LeanBin>
  </PropertyGroup>
  <ItemGroup>
    <Compile Remove="backtests/**;optimizations/**" />
    <!-- LEAN's own example algorithms are not a dependency of a user project -->
    <Reference Include="$(LeanBin)/QuantConnect.*.dll" Exclude="$(LeanBin)/QuantConnect.Algorithm.CSharp.dll" Private="false" />
    <Reference Include="$(LeanBin)/NodaTime.dll" Private="false" />
    <Reference Include="$(LeanBin)/Newtonsoft.Json.dll" Private="false" />
    <Reference Include="$(LeanBin)/Python.Runtime.dll" Private="false" />
  </ItemGroup>
</Project>
'''


def class_name(name: str) -> str:
    """'KRX Top 20' -> 'KRXTop20'; must be a valid Python/C# identifier."""
    parts = re.findall(r"[A-Za-z0-9]+", name)
    cls = "".join(p[:1].upper() + p[1:] for p in parts) or "KrxAlgorithm"
    return cls if not cls[0].isdigit() else "Krx" + cls


def create(ws: Workspace, name: str, language: str, template: str = "buy-hold") -> Path:
    if language not in ("python", "csharp"):
        raise KleanError(f"unknown language {language!r} (python or csharp)")
    if template not in TEMPLATES:
        raise KleanError(f"unknown template {template!r} ({', '.join(TEMPLATES)})")
    project = ws.root / name
    if project.exists():
        raise KleanError(f"{project} already exists")
    cls = class_name(Path(name).name)
    demo = (ws.data / "equity" / "krx" / "SYNTHETIC-DEMO-DATA.txt").exists()
    fmt = {"cls": cls, "code": "D00010" if demo else "005930",
           "code_note": ", a SYNTHETIC demo stock" if demo else ", Samsung Electronics"}
    project.mkdir(parents=True)
    if language == "python":
        main = {"buy-hold": PY_TEMPLATE.format(**fmt), "empty": PY_EMPTY.format(cls=cls),
                "top-market-cap": PY_TOP_MARKET_CAP.read_text(encoding="utf-8")}[template]
        (project / "main.py").write_text(main, encoding="utf-8")
        shutil.copy(PY_MODELS, project / "krx_models.py")
    else:
        main = {"buy-hold": CS_TEMPLATE.format(**fmt), "empty": CS_EMPTY.format(cls=cls),
                "top-market-cap": CS_TOP_MARKET_CAP.read_text(encoding="utf-8")}[template]
        (project / "Main.cs").write_text(main, encoding="utf-8")
        shutil.copy(CS_MODELS, project / "KrxModels.cs")
        (project / f"{cls}.csproj").write_text(CSPROJ_TEMPLATE.format(lean_bin=ws.launcher_dir), encoding="utf-8")
    return project


def delete(ws: Workspace, name: str) -> Path:
    """Remove a project folder (with its backtests). Only folders inside the workspace that are
    projects (main.py or a .csproj) can be deleted."""
    project = (ws.root / name).resolve()
    if project == ws.root or ws.root not in project.parents:
        raise KleanError(f"{project} isn't inside the workspace {ws.root}")
    if not project.is_dir():
        raise KleanError(f"{project} doesn't exist")
    language_of(project)  # raises unless it's a project
    shutil.rmtree(project)
    return project


def list_projects(ws: Workspace) -> list[Path]:
    out = []
    for p in sorted(ws.root.iterdir()):
        if p.is_dir() and p.name not in ("data", "storage") and not p.name.startswith("."):
            try:
                language_of(p)
                out.append(p)
            except KleanError:
                pass
    return out


def models_copy(project: Path) -> tuple[Path, Path]:
    """(the project's copy of the KRX models, krx-lean's current file)."""
    if language_of(project) == "python":
        return project / PY_MODELS.name, PY_MODELS
    return project / CS_MODELS.name, CS_MODELS


def models_state(project: Path) -> str:
    """"current", "differs" (krx-lean's models changed since the project was created, or the
    copy was edited) or "missing"."""
    copy, source = models_copy(project)
    if not copy.exists():
        return "missing"
    return "current" if copy.read_bytes() == source.read_bytes() else "differs"


def update_models(project: Path) -> Path | None:
    """Replace the project's copy with krx-lean's current models; the old copy is kept as
    ``<name>.bak``. Returns the backup path, or None if the copy was already current."""
    copy, source = models_copy(project)
    if models_state(project) == "current":
        return None
    backup = None
    if copy.exists():
        backup = copy.with_name(copy.name + ".bak")
        shutil.copy2(copy, backup)
    shutil.copy(source, copy)
    return backup


def models_row(ws: Workspace) -> tuple[str, bool, str]:
    """A `klean doctor` line: projects whose copy of the KRX models isn't krx-lean's current one.
    Informational (old tax/tick rules, or your own edits): it never fails the check."""
    stale = [p.name for p in list_projects(ws) if models_state(p) == "differs"]
    if not stale:
        return ("KRX models in projects", True, "all current")
    return ("KRX models in projects", True, f"note: {', '.join(stale)} differ from krx-lean's current models "
            "(`klean status models`, `klean update models NAME`)")


def language_of(project: Path) -> str:
    if list(project.glob("*.csproj")):
        return "csharp"
    if (project / "main.py").exists():
        return "python"
    raise KleanError(f"{project} has neither main.py nor a .csproj")


def python_algorithm_class(main_py: Path) -> str:
    """Name of the QCAlgorithm subclass in main.py."""
    tree = ast.parse(main_py.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if (isinstance(base, ast.Name) and base.id == "QCAlgorithm") or \
                        (isinstance(base, ast.Attribute) and base.attr == "QCAlgorithm"):
                    return node.name
    raise KleanError(f"no class deriving from QCAlgorithm in {main_py}")


def csharp_algorithm_class(project: Path) -> str:
    pattern = re.compile(r"class\s+(\w+)\s*:\s*QCAlgorithm\b")
    found = []
    for path in sorted(project.rglob("*.cs")):
        if path.relative_to(project).parts[0] in ("backtests", "optimizations", "obj", "bin"):
            continue
        found += pattern.findall(path.read_text(encoding="utf-8"))
    if len(found) != 1:
        raise KleanError(f"expected one class deriving from QCAlgorithm in {project}, found {found or 'none'}")
    return found[0]
