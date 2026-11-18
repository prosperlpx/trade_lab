"""Repository-backed checks for documented commands and interfaces."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_PATHS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


def fail(message: str) -> None:
    raise SystemExit(f"documentation verification failed: {message}")


def verify_local_links(doc_path: Path, text: str) -> None:
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if target.startswith(("https://", "http://", "mailto:", "#")):
            continue
        relative = target.split("#", 1)[0]
        if not relative:
            continue
        resolved = (doc_path.parent / relative).resolve()
        if not resolved.exists():
            fail(f"broken local link in {doc_path.relative_to(ROOT)}: {target}")


def verify_command_line(raw_line: str, source: str) -> None:
    line = raw_line.strip()
    if line.startswith("- run:"):
        line = line[len("- run:") :].strip()
    elif line.startswith("run:"):
        line = line[len("run:") :].strip()
    if not line or line.startswith("#") or line == "|":
        return

    match = re.match(r"^(?:python|python3|py)\s+(?:(-m)\s+)?([^\s]+)", line)
    if match:
        is_module, target = match.groups()
        if is_module:
            if target in {"pip", "venv", "pytest"}:
                return
            module_path = ROOT / (target.replace(".", "/") + ".py")
            package_path = ROOT / target.replace(".", "/") / "__main__.py"
            if not module_path.exists() and not package_path.exists():
                fail(f"unknown Python module in {source}: {target}")
        else:
            script_path = ROOT / target.replace("\\", "/")
            if not script_path.is_file():
                fail(f"unknown Python script in {source}: {target}")

    ruff = re.match(r"^ruff\s+check\s+(.+)$", line)
    if ruff:
        for target in ruff.group(1).split():
            if target.startswith("-"):
                continue
            if not (ROOT / target).exists():
                fail(f"unknown Ruff target in {source}: {target}")


def verify_commands(text: str, source: str) -> None:
    for block in re.findall(r"```[^\n]*\n(.*?)```", text, flags=re.DOTALL):
        for raw_line in block.splitlines():
            verify_command_line(raw_line, source)


def cli_options(module: Path) -> set[str]:
    tree = ast.parse(module.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            value = node.args[0].value
            if isinstance(value, str) and value.startswith("--"):
                found.add(value)
    return found


def verify_workflow_contract() -> None:
    trading_path = ROOT / ".github" / "workflows" / "trading_bot.yml"
    trading = trading_path.read_text(encoding="utf-8")
    ordered_markers = [
        "id: restore_state",
        "python -m trade_lab.cache_guard",
        "python -m trade_lab.live --prepare-alert",
        "key: ${{ steps.state.outputs.key }}-checkpoint",
        "python -m trade_lab.live --deliver-pending",
        "key: ${{ steps.state.outputs.key }}-final",
    ]
    positions = [trading.find(marker) for marker in ordered_markers]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        fail(
            "trading workflow no longer follows "
            "restore → guard → prepare → checkpoint → deliver → final-save order"
        )
    for required in (
        ".state/state.json",
        ".state/state.json.bak",
        "cache-matched-key",
        "restore-keys:",
        "cancel-in-progress: false",
        "if: success()",
        "github.event_name == 'schedule'",
        "--dry-run",
    ):
        if required not in trading:
            fail(f"trading workflow is missing required safety contract: {required}")

    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    required_checks = (
        "ruff check .",
        "pytest -q",
        "python scripts/verify_docs.py",
    )
    for required in required_checks:
        if required not in ci:
            fail(f"CI workflow is missing required check: {required}")


def main() -> int:
    missing_docs = [path for path in DOC_PATHS if not path.is_file()]
    if missing_docs:
        fail(f"missing documentation files: {missing_docs}")

    texts = {path: path.read_text(encoding="utf-8") for path in DOC_PATHS}
    combined = "\n".join(texts.values())

    for path, text in texts.items():
        verify_local_links(path, text)
        verify_commands(text, path.relative_to(ROOT).as_posix())

    actual_modules = {
        path.name for path in (ROOT / "trade_lab").glob("*.py") if path.name != "__init__.py"
    }
    architecture = texts[ROOT / "docs" / "architecture.md"]
    documented_modules = set(re.findall(r"^\| `([a-z_]+\.py)` \|", architecture, re.MULTILINE))
    if documented_modules != actual_modules:
        fail(
            "architecture module inventory differs from trade_lab/: "
            f"missing={sorted(actual_modules - documented_modules)}, "
            f"stale={sorted(documented_modules - actual_modules)}"
        )

    config_source = (ROOT / "trade_lab" / "config.py").read_text(encoding="utf-8")
    configured = set(re.findall(r'^\s*"([A-Z][A-Z0-9_]*)":\s*"[^"]+"', config_source, re.MULTILINE))
    runtime_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "trade_lab").glob("*.py")
    )
    runtime_vars = set(re.findall(r'os\.environ\.get\(["\']([A-Z][A-Z0-9_]*)["\']', runtime_source))
    documented_vars = set(
        re.findall(
            r"^\| `([A-Z][A-Z0-9_]*)` \|",
            texts[ROOT / "docs" / "configuration.md"],
            re.MULTILINE,
        )
    )
    required_vars = configured | runtime_vars
    if required_vars - documented_vars:
        fail(
            "undocumented application environment variables: "
            f"{sorted(required_vars - documented_vars)}"
        )

    config_tree = ast.parse(config_source)
    config_classes = {
        node.name: node for node in config_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name in {"StrategyConfig", "StrategyParameters"}
    }
    defaults: dict[str, object] = {}
    for class_name in ("StrategyParameters", "StrategyConfig"):
        for node in config_classes[class_name].body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                try:
                    defaults[node.target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    continue
    config_mapping = dict(
        re.findall(r'^\s*"([A-Z][A-Z0-9_]*)":\s*"([^"]+)"', config_source, re.MULTILINE)
    )
    table_defaults = {
        name: value
        for name, value in re.findall(
            r"^\| `([A-Z][A-Z0-9_]*)` \| ([^|]+) \|",
            texts[ROOT / "docs" / "configuration.md"],
            re.MULTILINE,
        )
    }
    for env_name, field_name in config_mapping.items():
        if field_name not in defaults or env_name not in table_defaults:
            fail(f"cannot verify documented default for {env_name}")
        try:
            documented_default = float(table_defaults[env_name].strip().strip("`"))
            implemented_default = float(defaults[field_name])
        except (TypeError, ValueError, OverflowError):
            fail(f"non-numeric default needs an explicit verifier rule: {env_name}")
        if documented_default != implemented_default:
            fail(
                f"default mismatch for {env_name}: docs={documented_default}, "
                f"code={implemented_default}"
            )

    live_source = (ROOT / "trade_lab" / "live.py").read_text(encoding="utf-8")
    state_default_match = re.search(
        r'os\.environ\.get\("STATE_FILE",\s*"([^"]+)"', live_source
    )
    if not state_default_match:
        fail("could not locate the STATE_FILE fallback in trade_lab/live.py")
    documented_state_default = table_defaults["STATE_FILE"].strip().strip("`")
    if documented_state_default != state_default_match.group(1):
        fail(
            "STATE_FILE default mismatch: "
            f"docs={documented_state_default}, code={state_default_match.group(1)}"
        )

    workflow_files = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    for workflow in workflow_files:
        workflow_text = workflow.read_text(encoding="utf-8")
        if workflow.name not in combined:
            fail(f"workflow is not referenced by documentation: {workflow.name}")
        workflow_vars = set(
            re.findall(r"^\s{10}([A-Z][A-Z0-9_]*)\s*:", workflow_text, re.MULTILINE)
        )
        workflow_secrets = set(
            re.findall(r"\$\{\{\s*secrets\.([A-Z][A-Z0-9_]*)\s*\}\}", workflow_text)
        )
        documented_names = set(re.findall(r"\b[A-Z][A-Z0-9_]*\b", combined))
        missing = (workflow_vars | workflow_secrets) - documented_names
        if missing:
            fail(f"undocumented workflow variables in {workflow.name}: {sorted(missing)}")
        workflow_source = workflow.relative_to(ROOT).as_posix()
        for workflow_line in workflow_text.splitlines():
            verify_command_line(workflow_line, workflow_source)

    verify_workflow_contract()

    live_options = cli_options(ROOT / "trade_lab" / "live.py")
    config_docs = texts[ROOT / "docs" / "configuration.md"]
    missing_live_options = {option for option in live_options if option not in config_docs}
    if missing_live_options:
        fail(f"undocumented live CLI options: {sorted(missing_live_options)}")

    cache_options = cli_options(ROOT / "trade_lab" / "cache_guard.py")
    operations_docs = texts[ROOT / "docs" / "operations.md"]
    missing_cache_options = {option for option in cache_options if option not in operations_docs}
    if missing_cache_options:
        fail(f"undocumented cache-guard CLI options: {sorted(missing_cache_options)}")

    print(
        "Documentation verified: "
        f"{len(DOC_PATHS)} Markdown files, {len(actual_modules)} package modules, "
        f"{len(required_vars)} application environment variables, "
        f"{len(live_options) + len(cache_options)} CLI options, "
        f"{len(workflow_files)} workflows."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
