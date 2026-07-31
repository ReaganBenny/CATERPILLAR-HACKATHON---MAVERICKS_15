"""
Reproduces the AWS Lambda deployment layout.

The zip flattens every module to the package root (/var/task/loader.py) while
data stays in a data/ subdirectory. The repo layout is different (src/loader.py
with data/ as a sibling of src/), so a loader that resolves its data directory
relative to the repo layout works locally and fails in Lambda with
FileNotFoundError: /var/data/telemetry.csv.

These tests build the flat layout in a temp directory and import from it, which
is the only way to catch that class of bug without deploying.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
DATA = REPO / "data"

# Mirrors the source blocks in infra/main.tf's archive_file.
LAMBDA_MODULES = ["lambda_handler.py", "analytics.py", "loader.py", "models.py"]


@pytest.fixture(scope="module")
def flat_package(tmp_path_factory):
    """A directory shaped exactly like the unzipped Lambda package."""
    root = tmp_path_factory.mktemp("var_task")
    for module in LAMBDA_MODULES:
        shutil.copy(SRC / module, root / module)
    shutil.copytree(DATA, root / "data")
    return root


def _run_in(package: Path, code: str):
    return subprocess.run([sys.executable, "-c", code], cwd=package,
                          capture_output=True, text=True)


def test_loader_finds_data_in_flat_lambda_layout(flat_package):
    result = _run_in(flat_package, "import loader; print(len(loader.load_equipment()))")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "7"


def test_telemetry_loads_in_flat_layout(flat_package):
    """The original failure: /var/data/telemetry.csv did not exist."""
    result = _run_in(flat_package, "import loader; print(len(loader.load_telemetry()))")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "11"


def test_handler_builds_payload_in_flat_layout(flat_package):
    """End-to-end: exactly what the Lambda runtime executes."""
    code = (
        "import json, lambda_handler as lh\n"
        "from datetime import date\n"
        "p = lh.build_payload(lh.load_equipment(), date(2025, 6, 1))\n"
        "print(json.dumps({'overdue': len(p['overdue']), "
        "'unassigned': len(p['unassigned']), 'notify': p['requires_notification']}))\n"
    )
    result = _run_in(flat_package, code)
    assert result.returncode == 0, result.stderr
    assert '"overdue": 5' in result.stdout
    assert '"unassigned": 2' in result.stdout
    assert '"notify": true' in result.stdout


def test_data_dir_env_override_wins(flat_package, tmp_path):
    elsewhere = tmp_path / "mounted"
    shutil.copytree(DATA, elsewhere)
    result = subprocess.run(
        [sys.executable, "-c", "import loader; print(loader.DATA_DIR)"],
        cwd=flat_package, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "DATA_DIR": str(elsewhere)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(elsewhere)


def test_terraform_ships_every_csv_the_loader_reads():
    """
    Guards the other half of the bug: the path was wrong AND three CSVs were
    missing from the archive. Keeps infra/main.tf honest against data/.
    """
    main_tf = (REPO / "infra" / "main.tf").read_text()
    packaged = set(re.findall(r'filename = "data/([^"]+)"', main_tf))
    on_disk = {p.name for p in DATA.glob("*.csv")}
    assert on_disk == packaged, (
        f"archive_file is missing: {on_disk - packaged}. "
        "Every CSV in data/ must ship or the Lambda raises FileNotFoundError."
    )


def test_terraform_ships_every_module_the_handler_imports():
    main_tf = (REPO / "infra" / "main.tf").read_text()
    packaged = set(re.findall(r'filename = "([^"/]+\.py)"', main_tf))
    assert set(LAMBDA_MODULES) == packaged
