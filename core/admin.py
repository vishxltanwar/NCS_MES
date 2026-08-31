# core/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    AuditLog,
    MagnetInsertion,
    MotorAssembly,
    Part,
    RotorBalancing,
    Serial,
    StatorTestingRecord,
    UserProfile,
)


class ImmutableTraceabilityAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

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


@admin.register(RotorBalancing)
class RotorBalancingAdmin(ImmutableTraceabilityAdminMixin, admin.ModelAdmin):
    list_display = ('serial_number', 'attempt_no', 'result', 'rotor_type', 'recorded_at', 'imported_at')
    list_filter = ('result', 'rotor_type')
    search_fields = ('serial_number',)
    list_per_page = 50


@admin.register(StatorTestingRecord)
class StatorTestingRecordAdmin(ImmutableTraceabilityAdminMixin, admin.ModelAdmin):
    list_display = ('serial_number', 'final_result', 'operator', 'recorded_at', 'imported_at')
    list_filter = ('final_result',)
    search_fields = ('serial_number', 'operator', 'code_number')
    list_per_page = 50


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


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'username', 'action', 'model_name', 'object_repr', 'object_pk')
    list_filter = ('action', 'model_name', 'username')
    search_fields = ('username', 'object_repr', 'object_pk', 'changes')
    readonly_fields = ('timestamp', 'user', 'username', 'action', 'model_name', 'object_pk', 'object_repr', 'changes')
    list_per_page = 100
    ordering = ('-timestamp',)
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Allow admin to delete old audit entries if needed
        return request.user.is_superuser

