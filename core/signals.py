# core/signals.py
# Auto-audit signals for all production-data models.
# Connected automatically when `core.models` is imported (via `from .models import *`).

import logging
import threading

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .models import (
    AuditLog,
    Serial,
    Part,
    RotorBalancing,
    StatorTestingRecord,
    MotorAssembly,
    MagnetInsertion,
)

logger = logging.getLogger(__name__)

# Thread-local storage for the current request user.
# Set by `bind_audit_user()` context manager in views.
_request_state = threading.local()


def bind_audit_user(user):
    """Bind a request user to audit signals for the duration of a with-block."""
    class _Bind:
        def __enter__(self):
            _request_state.user = user
            return self

        def __exit__(self, *args):
            _request_state.user = None
    return _Bind()


def _get_current_user():
    return getattr(_request_state, 'user', None)


def _safe_value(value):
    """Convert a model field value to a JSON-safe representation."""
    if hasattr(value, 'pk'):
        return str(value.pk)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(list(value), key=str)
    return value


def _snapshot(instance):
    """Return a dict of field name → value for the current instance."""
    return {f.name: _safe_value(getattr(instance, f.name, None)) for f in instance._meta.fields}


def _model_key(instance):
    return (instance.__class__, instance.pk)


# Thread-safe cache for pre-save snapshots.
_pre_save_cache = {}


def _register_audit(model_class):
    """Wire up pre/post save and post-delete signals for one model."""

    @receiver(pre_save, sender=model_class)
    def capture_old(sender, instance, **kwargs):
        # Capture old values only for existing objects (updates, not creates).
        if instance.pk:
            try:
                old = sender.objects.get(pk=instance.pk)
                _pre_save_cache[_model_key(instance)] = _snapshot(old)
            except sender.DoesNotExist:
                pass

    @receiver(post_save, sender=model_class)
    def log_save(sender, instance, created, **kwargs):
        user = _get_current_user()
        try:
            if created:
                AuditLog.objects.create(
                    action=AuditLog.AuditAction.CREATE,
                    model_name=instance._meta.model_name,
                    object_repr=str(instance)[:255],
                    object_pk=str(instance.pk)[:32] if instance.pk else '',
                    username=getattr(user, 'username', '') if user else '',
                    user=user if (user and user.pk) else None,
                )
            else:
                old = _pre_save_cache.pop(_model_key(instance), None)
                if old:
                    changes = {}
                    for field in instance._meta.fields:
                        name = field.name
                        if name.startswith('_') or name in ('id', 'pk'):
                            continue
                        new_val = _safe_value(getattr(instance, name, None))
                        old_val = old.get(name)
                        if new_val != old_val:
                            changes[name] = {'old': old_val, 'new': new_val}
                    changes = changes if changes else None
                else:
                    changes = None
                AuditLog.objects.create(
                    action=AuditLog.AuditAction.UPDATE,
                    model_name=instance._meta.model_name,
                    object_repr=str(instance)[:255],
                    object_pk=str(instance.pk)[:32] if instance.pk else '',
                    username=getattr(user, 'username', '') if user else '',
                    user=user if (user and user.pk) else None,
                    changes=changes,
                )
        except Exception as exc:
            logger.exception("Audit log save failed: %s", exc)

    @receiver(post_delete, sender=model_class)
    def log_delete(sender, instance, **kwargs):
        user = _get_current_user()
        try:
            AuditLog.objects.create(
                action=AuditLog.AuditAction.DELETE,
                model_name=instance._meta.model_name,
                object_repr=str(instance)[:255],
                object_pk=str(instance.pk)[:32] if instance.pk else '',
                username=getattr(user, 'username', '') if user else '',
                user=user if (user and user.pk) else None,
            )
        except Exception as exc:
            logger.exception("Audit log delete failed: %s", exc)


# Register all auditable production models.
for _model in (
    Serial,
    Part,
    RotorBalancing,
    StatorTestingRecord,
    MotorAssembly,
    MagnetInsertion,
):
    _register_audit(_model)
