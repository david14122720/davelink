"""
LinkSnap / Acortador — Shared SQLAlchemy Models

These models are used by FastAPI for direct DB access.
Django has its own ORM definitions (django_app/links/models.py)
that mirror this schema — Django ORM is the schema authority
that runs migrations.

If the schema drifts, run:
    python manage.py inspectdb > stubs.py
to regenerate and reconcile.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Link(Base):
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(10), unique=True, nullable=False, index=True)
    url_original = Column(Text, nullable=False)
    fecha_creacion = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    clicks = Column(Integer, default=0, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)

    # Relationships
    analytics_entries = relationship(
        "Analytics", back_populates="link", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Link(code={self.codigo!r}, active={self.activo})>"


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    link_id = Column(
        Integer,
        ForeignKey("links.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    referer = Column(Text, nullable=True)
    fecha_click = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    link = relationship("Link", back_populates="analytics_entries")

    def __repr__(self):
        return f"<Analytics(link_id={self.link_id}, at={self.fecha_click})>"


# Additional indexes (not covered by Column.index=True)
Index("idx_links_activo", Link.activo, postgresql_where=Link.activo == False)  # noqa: E712
Index("idx_analytics_fecha", Analytics.fecha_click.desc())
