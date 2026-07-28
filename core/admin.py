# core/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import Serial, Part, MotorAssembly, MagnetInsertion, UserProfile


class ImmutableTraceabilityAdminMixin:
    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)
        return actions


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'station', 'designation')
    list_filter = ('role', 'station')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'designation')


@admin.register(Serial)
class SerialAdmin(ImmutableTraceabilityAdminMixin, admin.ModelAdmin):
    list_display = (
        'serial_number', 'part_number', 'line_no', 'shift', 'part_type',
        'status', 'laser_delivery_status', 'created_at',
    )
    list_filter = ('shift', 'status', 'laser_delivery_status', 'part_type')
    search_fields = ('serial_number', 'part_number')


@admin.register(Part)
class PartAdmin(ImmutableTraceabilityAdminMixin, admin.ModelAdmin):
    list_display = ('serial_number', 'part_number', 'part_name', 'line_no', 'shift', 'added_by', 'created_at')
    list_filter = ('part_name', 'shift')
    search_fields = ('serial_number', 'part_number')


@admin.register(MagnetInsertion)
class MagnetInsertionAdmin(ImmutableTraceabilityAdminMixin, admin.ModelAdmin):
    list_display = ('stack_serial', 'magnet_serial', 'cycle_time', 'colored_result', 'shift', 'operator', 'timestamp')
    list_filter = ('pass_fail', 'shift')
    search_fields = ('stack_serial', 'magnet_serial')
    list_per_page = 50

    @admin.display(description='Result', ordering='pass_fail')
    def colored_result(self, obj):
        if obj.pass_fail:
            return format_html(
                '<span style="background:#3DAA6D;color:#fff;padding:3px 10px;border-radius:12px;font-weight:700;font-size:11px;">PASS</span>'
            )
        return format_html(
            '<span style="background:#e74c3c;color:#fff;padding:3px 10px;border-radius:12px;font-weight:700;font-size:11px;">FAIL</span>'
        )


# ── Admin Branding ──────────────────────────────────────────────────────────
@admin.register(MotorAssembly)
class MotorAssemblyAdmin(ImmutableTraceabilityAdminMixin, admin.ModelAdmin):
    list_display = ('motor_serial', 'rotor_serial', 'stator_serial', 'created_at', 'updated_at')
    search_fields = ('motor_serial', 'rotor_serial', 'stator_serial')
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 50


admin.site.site_header = "MES administration"
admin.site.site_title = "MES Admin Portal"
admin.site.index_title = "Welcome to MES Admin"

