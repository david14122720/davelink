"""
LinkSnap / Acortador — Django ORM Models

These models are the SCHEMA AUTHORITY for the database.
Django runs migrations; FastAPI reads via reflected SQLAlchemy models.

If you change these models, run:
    python manage.py makemigrations links
    python manage.py migrate
"""

from django.db import models


class Link(models.Model):
    """A shortened URL entry."""

    codigo = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        verbose_name="Short code",
        help_text="Unique 7-character base62 code",
    )
    url_original = models.TextField(
        verbose_name="Original URL",
        help_text="The long URL to redirect to",
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created at",
    )
    clicks = models.IntegerField(
        default=0,
        verbose_name="Click count",
    )
    activo = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text="Inactive links return 410 Gone",
    )

    class Meta:
        db_table = "links"
        verbose_name = "Link"
        verbose_name_plural = "Links"
        ordering = ["-fecha_creacion"]
        indexes = [
            models.Index(fields=["activo"], name="idx_links_activo"),
        ]

    def __str__(self):
        return f"{self.codigo} → {self.url_original[:60]}"


class Analytics(models.Model):
    """A single click/visit event on a shortened link."""

    link = models.ForeignKey(
        Link,
        on_delete=models.CASCADE,
        related_name="analytics_entries",
        verbose_name="Link",
    )
    ip_address = models.CharField(
        max_length=45,
        blank=True,
        null=True,
        verbose_name="IP Address",
    )
    user_agent = models.TextField(
        blank=True,
        default="",
        verbose_name="User Agent",
    )
    referer = models.TextField(
        blank=True,
        default="",
        verbose_name="Referer",
    )
    fecha_click = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Clicked at",
    )

    class Meta:
        db_table = "analytics"
        verbose_name = "Analytics Entry"
        verbose_name_plural = "Analytics Entries"
        ordering = ["-fecha_click"]
        indexes = [
            models.Index(fields=["-fecha_click"], name="idx_analytics_fecha"),
        ]

    def __str__(self):
        return f"Click on {self.link.codigo} at {self.fecha_click}"
