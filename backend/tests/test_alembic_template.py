"""Tests verifying that Alembic migration templates produce Ruff-compliant Python code."""

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mako.template import Template


def _comma_filter(val: Any) -> str:
    if isinstance(val, (list, tuple, Sequence)) and not isinstance(val, str):
        return ", ".join(str(v) for v in val)
    return str(val) if val is not None else ""


def test_alembic_template_renders_and_passes_ruff(tmp_path: Path) -> None:
    """Verify that a migration rendered from script.py.mako passes both Ruff check and format."""
    template_path = Path(__file__).resolve().parent.parent / "alembic" / "script.py.mako"
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    template = Template(filename=str(template_path))
    rendered = template.render(
        message="Initial test migration",
        up_revision="1a2b3c4d5e6f",
        down_revision=None,
        create_date="2026-10-21 00:00:00.000000",
        imports="",
        branch_labels=None,
        depends_on=None,
        upgrades="pass",
        downgrades="pass",
        comma=_comma_filter,
    )

    migration_file = tmp_path / "test_migration.py"
    migration_file.write_text(rendered, encoding="utf-8")

    # 1. Run Ruff check on the rendered migration file using pyproject.toml
    check_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            str(pyproject_path),
            str(migration_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    check_msg = f"Ruff check failed on migration:\n{check_result.stdout}\n{check_result.stderr}"
    assert check_result.returncode == 0, check_msg

    # 2. Run Ruff format --check on the rendered migration file
    format_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--config",
            str(pyproject_path),
            "--check",
            str(migration_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    format_msg = f"Ruff format failed on migration:\n{format_result.stdout}\n{format_result.stderr}"
    assert format_result.returncode == 0, format_msg


def test_alembic_template_renders_and_passes_ruff_with_previous_revision(tmp_path: Path) -> None:
    """Verify that a migration with down_revision passes both Ruff check and format."""
    template_path = Path(__file__).resolve().parent.parent / "alembic" / "script.py.mako"
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    template = Template(filename=str(template_path))
    rendered = template.render(
        message="Add user table",
        up_revision="2b3c4d5e6f7a",
        down_revision="1a2b3c4d5e6f",
        create_date="2026-10-21 01:00:00.000000",
        imports="import pgvector.sqlalchemy",
        branch_labels=None,
        depends_on=None,
        upgrades=(
            "op.create_table(\n"
            '        "items",\n'
            '        sa.Column("id", sa.Integer()),\n'
            '        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536)),\n'
            "    )"
        ),
        downgrades='op.drop_table("items")',
        comma=_comma_filter,
    )

    migration_file = tmp_path / "test_migration_2.py"
    migration_file.write_text(rendered, encoding="utf-8")

    # 1. Run Ruff check using backend configuration
    check_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            str(pyproject_path),
            str(migration_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    check_msg = f"Ruff check failed on migration:\n{check_result.stdout}\n{check_result.stderr}"
    assert check_result.returncode == 0, check_msg

    # 2. Run Ruff format --check
    format_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--config",
            str(pyproject_path),
            "--check",
            str(migration_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    format_msg = f"Ruff format failed on migration:\n{format_result.stdout}\n{format_result.stderr}"
    assert format_result.returncode == 0, format_msg
