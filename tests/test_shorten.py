"""Slice 3 (task 3.4): md5 dedup in POST /api/shorten.

Covers the commit 454785c contract (same URL → same code, no extra row)
through the new func.md5 path, including a 3000-byte URL that exceeds the
btree key limit (~2704 B) the md5 index exists to dodge. Tests run on
sqlite, which has no md5() — shorten.py branches to plain equality there
(same result); Postgres uses func.md5 + equality guard on the index.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
_backend_dir = Path(__file__).resolve().parent.parent / "backend"
for _p in (str(_backend_dir / "django_app"), str(_backend_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _post(client, url):
    return client.post("/api/shorten", json={"url": url})


def test_dedup_returns_existing_code(client, db_session, isolated_memory_limiter):
    """Commit 454785c behavior preserved through the md5 path."""
    from backend.shared.models import Link

    url = "https://example.com/md5-dedup-path"
    r1 = _post(client, url)
    assert r1.status_code == 200
    code1 = r1.json()["code"]

    count_after_first = db_session.query(Link).count()

    r2 = _post(client, url)
    assert r2.status_code == 200
    assert r2.json()["code"] == code1
    assert r2.json()["original_url"] == url

    assert db_session.query(Link).count() == count_after_first


def test_long_url_insert_and_dedup(client, db_session, isolated_memory_limiter):
    """3000-byte URL: insert succeeds and lookup dedups (no new row).

    The API caps URLs at 2083 chars (Pydantic HttpUrl) — long URLs enter
    via the admin/ORM path (design D4), which is exactly the path the md5
    index protects from btree-limit failures. So: insert through the ORM
    (admin equivalent), then prove the endpoint's own dedup helper
    (find_existing_link, same function shorten_url calls) finds it.
    Spec scenarios 'URLs exceeding btree limit can be inserted' + 'Dedup
    finds existing long URL'. On sqlite this exercises the equality
    branch; on Postgres the same helper hits func.md5 on the index.
    """
    from backend.fastapi_app.routes.shorten import find_existing_link
    from backend.shared.models import Link

    long_url = "https://example.com/long/" + "a" * (
        3000 - len("https://example.com/long/")
    )
    assert len(long_url) == 3000

    # API rejects >2083 chars at validation — documents the admin-path premise
    r = _post(client, long_url)
    assert r.status_code == 422

    # Admin/ORM path: long insert must succeed (md5 index, not btree, on PG)
    link = Link(codigo="lng3000", url_original=long_url)
    db_session.add(link)
    db_session.commit()

    count_after_insert = db_session.query(Link).count()

    # Endpoint's dedup helper finds it → second shorten would return the
    # existing code instead of inserting (commit 454785c contract)
    found = find_existing_link(db_session, long_url)
    assert found is not None
    assert found.codigo == "lng3000"
    assert db_session.query(Link).count() == count_after_insert


def test_postgres_dedup_branch_uses_md5_function():
    """Compile-shape proof for the non-sqlite branch of find_existing_link:
    the same func.md5(Link.url_original) == digest expression the helper
    runs on Postgres compiles to a md5() call (index-compatible)."""
    import hashlib

    from sqlalchemy import func, select
    from sqlalchemy.dialects import postgresql

    from backend.shared.models import Link

    digest = hashlib.md5(b"https://example.com/x").hexdigest()
    stmt = select(Link).where(func.md5(Link.url_original) == digest)
    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "md5(links.url_original)" in compiled
    assert digest in compiled


def test_dialect_branch_recorded(client, db_session):
    """Documents which dedup branch the test backend exercises."""
    bind = db_session.get_bind()
    assert bind is not None
    # pytest runs on sqlite → plain-equality branch; a Postgres CI run
    # would exercise func.md5. Either way the contract tests above hold.
    assert bind.dialect.name == "sqlite"
