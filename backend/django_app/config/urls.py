"""
Django URL Configuration for LinkSnap / Acortador.
"""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]

# Customize admin header
admin.site.site_header = "LinkSnap Administration"
admin.site.site_title = "LinkSnap Admin"
admin.site.index_title = "Welcome to LinkSnap Admin"
