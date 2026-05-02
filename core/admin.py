# core/admin.py
from django.contrib import admin
from .models import Serial, Part


@admin.register(Serial)
class SerialAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'part_number', 'line_no', 'shift', 'part_type', 'status', 'created_at')
    list_filter = ('shift', 'status', 'part_type')
    search_fields = ('serial_number', 'part_number')


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'part_number', 'part_name', 'line_no', 'shift', 'added_by', 'created_at')
    list_filter = ('part_name', 'shift')
    search_fields = ('serial_number', 'part_number')


# ── Admin Branding ──────────────────────────────────────────────────────────
admin.site.site_header = "MES administration"
admin.site.site_title = "MES Admin Portal"
admin.site.index_title = "Welcome to MES Admin"

