"""
LinkSnap / Acortador — FastAPI SQLAlchemy Models (Reflected)

Uses automap_base() to reflect the existing database schema
created by Django migrations. This keeps FastAPI in sync
without maintaining a separate model definition.

If the Django models change and tables are migrated, these
reflected models automatically pick up new columns.
"""

from sqlalchemy.ext.automap import automap_base

from shared.database import engine

# Reflect the database schema into automap base
Base = automap_base()
Base.prepare(autoload_with=engine)

# Expose reflected classes with clean names
Link = Base.classes.links
Analytics = Base.classes.analytics

__all__ = ["Base", "Link", "Analytics"]
