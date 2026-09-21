"""Guards on how config/clickhouse/init.sql is written and applied.

Two failures motivated these tests:

1. CI POSTed the whole file to ClickHouse's HTTP interface, which runs one
   statement per request and answered `Code: 62 ... Multi-statements are not
   allowed` (surfacing only as `curl` exit 22).
2. The Helm bootstrap Job split the file on ';' and dropped fragments starting
   with '--'. Because every statement sits under a comment block, that filter
   discarded the statement along with its comment: 8 statements became 3
   unrunnable ones, so the pre-install hook never created the schema.

Both appliers now share the same splitting rule, and the schema is
database-qualified because neither of them carries a session (no `USE kato`).
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_SQL = REPO_ROOT / "config" / "clickhouse" / "init.sql"
MIRRORS = [
    REPO_ROOT / "deployment" / "config" / "clickhouse" / "init.sql",
    REPO_ROOT / "charts" / "kato" / "scripts" / "init.sql",
]
EXPECTED_TABLES = ["patterns_data", "lsh_buckets", "pattern_stats", "patterns_metadata"]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


applier = _load_module(REPO_ROOT / "scripts" / "apply_clickhouse_schema.py", "apply_clickhouse_schema")
bootstrap = _load_module(REPO_ROOT / "charts" / "kato" / "scripts" / "bootstrap.py", "helm_bootstrap")

SPLITTERS = pytest.mark.parametrize(
    "split",
    [applier.split_statements, bootstrap.split_statements],
    ids=["apply_clickhouse_schema", "helm_bootstrap"],
)


@SPLITTERS
def test_every_statement_survives_its_comment_block(split):
    """A statement preceded by comments must not be dropped with them."""
    statements = split(CANONICAL_SQL.read_text())

    assert len(statements) == 8, f"expected 8 statements, got {len(statements)}: {statements}"
    assert statements[0].startswith("CREATE DATABASE IF NOT EXISTS kato")
    for statement in statements:
        assert not statement.startswith("--")
        assert "--" not in statement


@SPLITTERS
def test_each_table_is_created_exactly_once(split):
    statements = split(CANONICAL_SQL.read_text())
    for table in EXPECTED_TABLES:
        creates = [s for s in statements if s.startswith(f"CREATE TABLE IF NOT EXISTS kato.{table}")]
        assert len(creates) == 1, f"{table}: expected 1 CREATE, got {len(creates)}"


@SPLITTERS
def test_splitters_agree(split):
    assert split(CANONICAL_SQL.read_text()) == applier.split_statements(CANONICAL_SQL.read_text())


def test_schema_is_database_qualified_and_sessionless():
    """No `USE`: HTTP appliers send one statement per request with no session,
    so unqualified names would land the tables in `default`."""
    statements = applier.split_statements(CANONICAL_SQL.read_text())

    assert not any(s.upper().startswith("USE ") for s in statements)
    for statement in statements:
        for verb in ("CREATE TABLE IF NOT EXISTS ", "ALTER TABLE "):
            if statement.startswith(verb):
                target = statement[len(verb) :].split()[0]
                assert target.startswith("kato."), f"unqualified table reference: {target}"


@pytest.mark.parametrize("mirror", MIRRORS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_mirrors_match_canonical_schema(mirror):
    assert mirror.read_text() == CANONICAL_SQL.read_text()
