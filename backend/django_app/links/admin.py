"""
LinkSnap / Acortador — Django Admin Configuration
"""

from django.contrib import admin, messages

from .models import Analytics, Link


class ClickInline(admin.TabularInline):
    """Show last 50 click events on the Link detail page."""

    model = Analytics
    fields = ("ip_address", "user_agent", "referer", "fecha_click")
    readonly_fields = fields
    ordering = ("-fecha_click",)
    max_num = 50
    can_delete = False
    show_change_link = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Link)
class LinkAdmin(admin.ModelAdmin):
    list_display = ("codigo", "truncated_url", "fecha_creacion", "clicks", "activo")
    list_filter = ("activo", "fecha_creacion")
    search_fields = ("codigo", "url_original")
    list_per_page = 100
    ordering = ("-fecha_creacion",)
    inlines = [ClickInline]

    fieldsets = (
        (None, {
            "fields": ("codigo", "url_original", "activo"),
        }),
        ("Statistics", {
            "fields": ("clicks", "fecha_creacion"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("clicks", "fecha_creacion")

    actions = ("mark_active", "mark_inactive")

    @admin.display(description="Original URL")
    def truncated_url(self, obj):
        return obj.url_original[:80] + "…" if len(obj.url_original) > 80 else obj.url_original

    @admin.action(description="Mark selected links as active")
    def mark_active(self, request, queryset):
        updated = queryset.update(activo=True)
        self.message_user(request, f"{updated} link(s) marked as active.", messages.SUCCESS)

    @admin.action(description="Mark selected links as inactive")
    def mark_inactive(self, request, queryset):
        updated = queryset.update(activo=False)
        self.message_user(request, f"{updated} link(s) marked as inactive.", messages.WARNING)
