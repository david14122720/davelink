"""Slice 3 (task 3.2): 0003 md5-index migration structure + dialect branch.

Postgres is the authoritative target (CONCURRENTLY, reversible). SQLite —
the pytest/Django-test backend — has NO md5() function and rejects even
CREATE INDEX of the expression (OperationalError: no such function: md5,
verified empirically), so the forward step must skip gracefully there
instead of breaking `migrate` / test-DB setup.
"""

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# ── Django path bootstrap (same as test_admin; needed for focused runs
# where test_admin wasn't imported first) ──
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
_backend_dir = Path(__file__).resolve().parent.parent / "backend"
_django_app_dir = _backend_dir / "django_app"
for _p in (str(_django_app_dir), str(_backend_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

migration = importlib.import_module("links.migrations.0003_md5_index")


class StubEditor:
    """Minimal schema_editor stand-in: captures SQL per vendor."""

    def __init__(self, vendor, fail_on_execute=False):
        self.connection = SimpleNamespace(vendor=vendor)
        self.executed = []
        self._fail = fail_on_execute

    def execute(self, sql):
        if self._fail:
            raise Exception("no such function: md5")
        self.executed.append(sql)


def test_migration_is_non_atomic_and_chained_on_0002():
    assert migration.Migration.atomic is False
    assert ("links", "0002_alter_analytics_ip_address") in (
        migration.Migration.dependencies
    )


def test_postgres_path_uses_create_index_concurrently():
    editor = StubEditor("postgresql")
    migration.create_md5_index(None, editor)
    assert len(editor.executed) == 1
    sql = editor.executed[0]
    assert "CREATE INDEX CONCURRENTLY" in sql
    assert "idx_links_url_md5" in sql
    assert "md5(url_original)" in sql


def test_sqlite_path_uses_plain_index_and_never_concurrently():
    editor = StubEditor("sqlite")
    migration.create_md5_index(None, editor)
    assert len(editor.executed) == 1
    sql = editor.executed[0]
    assert "CONCURRENTLY" not in sql
    assert "idx_links_url_md5" in sql


def test_sqlite_operational_error_skips_gracefully():
    """Simulates real sqlite (no md5 func): must not raise, must not
    break Django test-DB creation."""
    editor = StubEditor("sqlite", fail_on_execute=True)
    migration.create_md5_index(None, editor)  # must not raise
    assert editor.executed == []


def test_reverse_drops_index():
    editor = StubEditor("postgresql")
    migration.drop_md5_index(None, editor)
    assert editor.executed == [migration.REVERSE_SQL]
    assert "DROP INDEX" in editor.executed[0]
    assert "idx_links_url_md5" in editor.executed[0]


@pytest.mark.django_db
def test_migrate_runs_clean_on_sqlite():
    """The real proof: Django test-DB setup (which runs migrations,
    including 0003) works on sqlite — exercised implicitly by every
    django_db test in this session, asserted explicitly here."""
    from django.db import connection

    tables = connection.introspection.table_names()
    assert "links" in tables
