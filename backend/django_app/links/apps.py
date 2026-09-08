from django.apps import AppConfig


class LinksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "links"
    verbose_name = "Links"

    def ready(self):
        # Import receivers so post_save/post_delete invalidation is active
        # on every entrypoint: manage.py AND get_wsgi_application() under
        # the FastAPI ASGI mount (fastapi_app/main.py imports cache first,
        # so there is no import cycle — see design § Signal Wiring).
        from . import signals  # noqa: F401
