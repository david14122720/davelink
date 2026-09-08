# Slice 3 data layer: md5(url_original) expression index for dedup lookups.
#
# A plain btree on url_original (Text) fails for URLs past ~2704 bytes, but
# the admin UI allows longer URLs than the API's 2083-char cap — so dedup
# hashes with md5() (32 bytes, always indexable). Django's Index can't
# express md5(), hence raw SQL. Postgres builds it CONCURRENTLY (no write
# lock); the migration is non-atomic and fully reversible.
#
# SQLite (test env) has NO md5() function — it rejects even CREATE INDEX of
# the expression. The forward step therefore skips gracefully there (Django
# test DBs never need the index; sqlite dedup uses plain equality — see
# routes/shorten.py). Verified: sqlite raises OperationalError
# "no such function: md5" at CREATE INDEX time.

from django.db import migrations

PG_SQL = (
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_links_url_md5 "
    "ON links (md5(url_original));"
)
SQLITE_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_links_url_md5 "
    "ON links (md5(url_original));"
)
REVERSE_SQL = "DROP INDEX IF EXISTS idx_links_url_md5;"


def create_md5_index(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        # CONCURRENTLY cannot run inside a transaction block — the
        # migration is atomic=False below, so this is safe.
        schema_editor.execute(PG_SQL)
    else:
        # SQLite / other backends: best effort only. SQLite lacks md5()
        # entirely, so skip instead of breaking `migrate` / test DB setup.
        try:
            schema_editor.execute(SQLITE_SQL)
        except Exception as exc:
            print(f"Skipping idx_links_url_md5 on {vendor}: {exc}")


def drop_md5_index(apps, schema_editor):
    try:
        schema_editor.execute(REVERSE_SQL)
    except Exception as exc:
        print(f"Skipping drop of idx_links_url_md5 on "
              f"{schema_editor.connection.vendor}: {exc}")


class Migration(migrations.Migration):
    # Required for CREATE INDEX CONCURRENTLY on Postgres.
    atomic = False

    dependencies = [
        ('links', '0002_alter_analytics_ip_address'),
    ]

    operations = [
        migrations.RunPython(create_md5_index, drop_md5_index),
    ]
