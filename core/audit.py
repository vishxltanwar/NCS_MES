# core/audit.py
# Audit logging helpers for the MES system.
#
# The AuditLog model lives in models.py (discovered by Django migrations).
# Use the helpers here in views to log bulk imports or requests with extra context.

from .models import AuditLog


def log_action(action, instance, user=None, changes=None):
    """
    Create a single audit log entry for `instance`.

    Usage in views:
        from .audit import log_action, AuditAction
        log_action(AuditAction.CREATE, serial_obj, request.user)
        log_action(AuditAction.IMPORT, batch_obj, request.user,
                   changes={'imported': 50, 'source': 'rotor_balancing.csv'})
    """
    from django.utils import timezone

    username = ''
    if user:
        username = getattr(user, 'username', '') or ''
    object_repr = str(instance)[:255]
    object_pk = str(instance.pk)[:32] if instance.pk else ''

    AuditLog.objects.create(
        action=action,
        model_name=instance._meta.model_name,
        object_repr=object_repr,
        object_pk=object_pk,
        username=username,
        user=user if (user and user.pk) else None,
        changes=changes or {},
        timestamp=timezone.now(),
    )
