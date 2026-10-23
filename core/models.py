# core/models.py
# Napino MES — Django ORM models
from django.db import models
from django.contrib.auth.models import User
from django.db.models.functions import Lower
from django.db.models.signals import post_save
from django.dispatch import receiver
from .rbac import ROLE_CHOICES, ROLE_VIEWER, STATION_CHOICES


def _normalize_identifier(value):
    if value is None:
        return None
    return str(value).strip().upper()


PART_TYPE_ROTOR = 'Rotor'
PART_TYPE_STATOR = 'Stator'
PART_TYPE_MOTOR = 'Motor'
PART_TYPE_CHOICES = [
    (PART_TYPE_ROTOR, PART_TYPE_ROTOR),
    (PART_TYPE_STATOR, PART_TYPE_STATOR),
    (PART_TYPE_MOTOR, PART_TYPE_MOTOR),
]
PART_TYPES = tuple(value for value, _label in PART_TYPE_CHOICES)


def normalize_part_type(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return next((part_type for part_type in PART_TYPES if part_type.casefold() == normalized), None)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    station = models.CharField(max_length=40, choices=STATION_CHOICES, blank=True, default='')
    designation = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        db_table = 'user_profiles'
        ordering = ['user__username']

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


class Serial(models.Model):
    LASER_DELIVERY_PENDING = 'Pending'
    LASER_DELIVERY_DELIVERED = 'Delivered'
    LASER_DELIVERY_FAILED = 'Failed'
    LASER_DELIVERY_CHOICES = [
        (LASER_DELIVERY_PENDING, 'Pending'),
        (LASER_DELIVERY_DELIVERED, 'Delivered'),
        (LASER_DELIVERY_FAILED, 'Failed'),
    ]

    serial_number = models.CharField(max_length=32, unique=True, db_index=True)
    part_number   = models.CharField(max_length=10, default='', db_index=True)
    line_no       = models.CharField(max_length=4, default='', db_index=True)
    shift         = models.CharField(max_length=2, default='', db_index=True)
    part_type     = models.CharField(max_length=20, choices=PART_TYPE_CHOICES, db_index=True)
    created_at    = models.DateTimeField(auto_now_add=True, db_index=True)
    status        = models.CharField(max_length=20, default='Pending', db_index=True)
    laser_delivery_status = models.CharField(
        max_length=12,
        choices=LASER_DELIVERY_CHOICES,
        default=LASER_DELIVERY_PENDING,
        db_default=LASER_DELIVERY_PENDING,
        db_index=True,
    )
    laser_delivery_error = models.CharField(
        max_length=255,
        blank=True,
        default='',
        db_default='',
    )

    class Meta:
        db_table = 'serials'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'part_type'], name='serial_created_part_idx'),
            models.Index(fields=['part_type', '-created_at'], name='serial_part_created_idx'),
            models.Index(fields=['status', '-created_at'], name='serial_status_created_idx'),
        ]
        constraints = [
            models.UniqueConstraint(Lower('serial_number'), name='serial_number_ci_unique'),
            models.CheckConstraint(
                condition=models.Q(part_type__in=PART_TYPES),
                name='serial_part_type_valid',
            ),
        ]

    def save(self, *args, **kwargs):
        self.serial_number = _normalize_identifier(self.serial_number)
        self.part_type = normalize_part_type(self.part_type) or self.part_type
        super().save(*args, **kwargs)

    def __str__(self):
        return self.serial_number


class DailySerialCounter(models.Model):
    production_date = models.DateField(unique=True)
    last_sequence = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'daily_serial_counters'
        ordering = ['-production_date']

    def __str__(self):
        return f"{self.production_date}: {self.last_sequence}"


class LoginThrottle(models.Model):
    key = models.CharField(max_length=80, unique=True)
    failure_count = models.PositiveIntegerField(default=0)
    window_started_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'login_throttles'

    def __str__(self):
        return f"{self.key}: {self.failure_count}"


class Part(models.Model):
    serial_number = models.CharField(max_length=32, unique=True, null=True, blank=True, db_index=True)
    part_number   = models.CharField(max_length=10, db_index=True)
    part_name     = models.CharField(max_length=50, choices=PART_TYPE_CHOICES)
    line_no       = models.CharField(max_length=4)
    shift         = models.CharField(max_length=2)
    created_at    = models.DateTimeField(auto_now_add=True)
    added_by      = models.CharField(max_length=100, default='')

    class Meta:
        db_table = 'parts'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(Lower('serial_number'), name='part_serial_number_ci_unique'),
            models.CheckConstraint(
                condition=models.Q(part_name__in=PART_TYPES),
                name='part_name_valid',
            ),
        ]

    def save(self, *args, **kwargs):
        self.serial_number = _normalize_identifier(self.serial_number)
        self.part_name = normalize_part_type(self.part_name) or self.part_name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.part_name} — {self.part_number}"


class RotorBalancing(models.Model):
    serial_number = models.CharField(max_length=32, db_index=True)
    attempt_no    = models.IntegerField(default=1, db_index=True)
    result        = models.CharField(max_length=10, choices=[('Pass', 'Pass'), ('Fail', 'Fail')], db_index=True)
    rotor_type    = models.CharField(max_length=100, null=True, blank=True)
    recorded_at   = models.DateTimeField(null=True, blank=True, db_index=True)
    measure_run   = models.IntegerField(null=True, blank=True)
    balancing_run = models.IntegerField(null=True, blank=True)
    rpm           = models.IntegerField(null=True, blank=True)
    plane1_weight = models.FloatField(null=True, blank=True)
    plane1_degree = models.FloatField(null=True, blank=True)
    plane2_weight = models.FloatField(null=True, blank=True)
    plane2_degree = models.FloatField(null=True, blank=True)
    imported_at   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'rotor_balancing'
        ordering = ['-imported_at']
        indexes = [
            models.Index(fields=['serial_number', 'attempt_no']),
            models.Index(fields=['-imported_at', 'result'], name='rotor_imported_result_idx'),
            models.Index(fields=['-recorded_at'], name='rotor_recorded_at_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower('serial_number'),
                models.F('attempt_no'),
                name='rotor_serial_attempt_ci_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_no__gt=0),
                name='rotor_attempt_number_positive',
            ),
        ]

    def save(self, *args, **kwargs):
        self.serial_number = _normalize_identifier(self.serial_number)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} attempt {self.attempt_no} - {self.result}"

class StatorTestingRecord(models.Model):
    serial_number = models.CharField(max_length=32, db_index=True)
    recorded_at = models.DateTimeField(null=True, blank=True, db_index=True)
    final_result = models.CharField(max_length=20, db_index=True)
    
    # Meta
    operator = models.CharField(max_length=100, null=True, blank=True)
    code_number = models.CharField(max_length=100, null=True, blank=True)
    symmetry = models.CharField(max_length=50, null=True, blank=True)
    
    # Resistance Tests
    ry = models.CharField(max_length=50, null=True, blank=True)
    ry_result = models.CharField(max_length=20, null=True, blank=True)
    yb = models.CharField(max_length=50, null=True, blank=True)
    yb_result = models.CharField(max_length=20, null=True, blank=True)
    br = models.CharField(max_length=50, null=True, blank=True)
    br_result = models.CharField(max_length=20, null=True, blank=True)
    
    # Electrical Tests
    thd_win = models.CharField(max_length=50, null=True, blank=True)
    thd_result = models.CharField(max_length=20, null=True, blank=True)
    ir_m_ohms = models.CharField(max_length=50, null=True, blank=True)
    ir_result = models.CharField(max_length=20, null=True, blank=True)
    high_voltage = models.CharField(max_length=50, null=True, blank=True)
    hv_result = models.CharField(max_length=20, null=True, blank=True)
    
    # Surge Tests
    surge_voltage = models.CharField(max_length=50, null=True, blank=True)
    surge_main_ry_error = models.CharField(max_length=50, null=True, blank=True)
    surge_ry_result = models.CharField(max_length=20, null=True, blank=True)
    surge_aux_yb_error = models.CharField(max_length=50, null=True, blank=True)
    surge_aux_yb_result = models.CharField(max_length=20, null=True, blank=True)
    surge_main_aux_br_error = models.CharField(max_length=50, null=True, blank=True)
    surge_main_aux_br_result = models.CharField(max_length=20, null=True, blank=True)
    
    # Inductance Tests
    inductance_1 = models.CharField(max_length=50, null=True, blank=True)
    l1_result = models.CharField(max_length=20, null=True, blank=True)
    inductance_2 = models.CharField(max_length=50, null=True, blank=True)
    l2_result = models.CharField(max_length=20, null=True, blank=True)
    inductance_3 = models.CharField(max_length=50, null=True, blank=True)
    l3_result = models.CharField(max_length=20, null=True, blank=True)
    
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stator_testing'
        ordering = ['-imported_at']
        indexes = [
            models.Index(fields=['-imported_at', 'final_result'], name='stator_imported_result_idx'),
            models.Index(fields=['-recorded_at'], name='stator_recorded_at_idx'),
        ]
    def save(self, *args, **kwargs):
        self.serial_number = _normalize_identifier(self.serial_number)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.final_result}"


class MotorAssembly(models.Model):
    motor_serial = models.CharField(max_length=32, unique=True, db_index=True)
    rotor_serial = models.CharField(max_length=32, unique=True, db_index=True)
    stator_serial = models.CharField(max_length=32, unique=True, db_index=True)
    final_motor_serial = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    motor_serial_assigned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'motor_assembly'
        ordering = ['-updated_at']
        verbose_name_plural = 'motor assemblies'
        constraints = [
            models.UniqueConstraint(Lower('motor_serial'), name='motor_serial_ci_unique'),
            models.UniqueConstraint(Lower('rotor_serial'), name='motor_rotor_serial_ci_unique'),
            models.UniqueConstraint(Lower('stator_serial'), name='motor_stator_serial_ci_unique'),
        ]

    def save(self, *args, **kwargs):
        self.motor_serial = _normalize_identifier(self.motor_serial)
        self.rotor_serial = _normalize_identifier(self.rotor_serial)
        self.stator_serial = _normalize_identifier(self.stator_serial)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.motor_serial} = {self.rotor_serial} + {self.stator_serial}"


class MagnetInsertion(models.Model):
    SHIFT_CHOICES = [('A', 'A'), ('B', 'B'), ('C', 'C'), ('G', 'G')]

    stack_serial  = models.CharField(max_length=64, db_index=True)
    magnet_serial = models.CharField(max_length=64, db_index=True)
    cycle_time    = models.FloatField(help_text='Cycle time in seconds')
    pass_fail     = models.BooleanField(default=True, help_text='True=PASS, False=FAIL')
    shift         = models.CharField(max_length=1, choices=SHIFT_CHOICES)
    operator      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'magnet_insertion'
        ordering = ['-timestamp']
        constraints = [
            models.UniqueConstraint(
                Lower('stack_serial'),
                Lower('magnet_serial'),
                name='magnet_stack_pair_ci_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(cycle_time__gt=0, cycle_time__lte=3600),
                name='magnet_cycle_time_valid',
            ),
        ]

    def save(self, *args, **kwargs):
        self.stack_serial = _normalize_identifier(self.stack_serial)
        self.magnet_serial = _normalize_identifier(self.magnet_serial)
        super().save(*args, **kwargs)

    def __str__(self):
        result = 'PASS' if self.pass_fail else 'FAIL'
        return f"{self.stack_serial} - {result}"


# ── Operation Gates (MES process steps) ───────────────────────────────────────
OPERATION_ENTITY_ROTOR = 'rotor'
OPERATION_ENTITY_STATOR = 'stator'
OPERATION_ENTITY_MOTOR = 'motor'
OPERATION_ENTITY_CHOICES = [
    (OPERATION_ENTITY_ROTOR, 'Rotor'),
    (OPERATION_ENTITY_STATOR, 'Stator'),
    (OPERATION_ENTITY_MOTOR, 'Motor'),
]

# Rotor operation codes
OP_MAGNET_INSERTION = 'MAGNET_INSERTION'
OP_YOKE_SHAFT_PRESSING = 'YOKE_SHAFT_PRESSING'
OP_ROTOR_BALANCING = 'ROTOR_BALANCING'
OP_ROTOR_OP70 = 'ROTOR_OP70'
OP_ROTOR_OP80 = 'ROTOR_OP80'
OP_ROTOR_RELEASE = 'ROTOR_RELEASE'
# Stator operation codes
OP_STATOR_OP120 = 'STATOR_OP120'
OP_STATOR_RELEASE = 'STATOR_RELEASE'
# Motor operation codes
OP_MOTOR_OP10 = 'MOTOR_OP10'
OP_MOTOR_OP70 = 'MOTOR_OP70'
OP_MOTOR_OP90 = 'MOTOR_OP90'
OP_MOTOR_OP100 = 'MOTOR_OP100'
OP_MOTOR_SERIAL_ASSIGN = 'MOTOR_SERIAL_ASSIGN'
OP_MOTOR_OP120 = 'MOTOR_OP120'
OP_FINAL_INSPECTION = 'FINAL_INSPECTION'
OP_DISPATCH_RELEASE = 'DISPATCH_RELEASE'

OPERATION_CODE_CHOICES = [
    (OP_MAGNET_INSERTION, 'Magnet insertion'),
    (OP_YOKE_SHAFT_PRESSING, 'Yoke and shaft pressing'),
    (OP_ROTOR_BALANCING, 'Rotor balancing'),
    (OP_ROTOR_OP70, 'OP70 Front plate and bearing assembly'),
    (OP_ROTOR_OP80, 'OP80 Front plate and rotor assembly'),
    (OP_ROTOR_RELEASE, 'Rotor release'),
    (OP_STATOR_OP120, 'OP120 Final stator assembly testing'),
    (OP_STATOR_RELEASE, 'Stator release'),
    (OP_MOTOR_OP10, 'OP10 Front lid and stator assembly'),
    (OP_MOTOR_OP70, 'OP70 Resistance, HV, and IR test'),
    (OP_MOTOR_OP90, 'OP90 Motor EOL test'),
    (OP_MOTOR_OP100, 'OP100 4Q EOL test'),
    (OP_MOTOR_SERIAL_ASSIGN, 'Motor serial assignment'),
    (OP_MOTOR_OP120, 'OP120 Laser marking and nameplate assembly'),
    (OP_FINAL_INSPECTION, 'Final inspection'),
    (OP_DISPATCH_RELEASE, 'Dispatch release'),
]

OPERATION_STATUS_COMPLETED = 'Completed'
OPERATION_STATUS_FAILED = 'Failed'
OPERATION_STATUS_CHOICES = [
    (OPERATION_STATUS_COMPLETED, 'Completed'),
    (OPERATION_STATUS_FAILED, 'Failed'),
]


class OperationRecord(models.Model):
    entity_type = models.CharField(max_length=10, choices=OPERATION_ENTITY_CHOICES, db_index=True)
    serial_number = models.CharField(max_length=64, db_index=True)
    operation_code = models.CharField(max_length=40, choices=OPERATION_CODE_CHOICES, db_index=True)
    status = models.CharField(max_length=12, choices=OPERATION_STATUS_CHOICES, default=OPERATION_STATUS_COMPLETED, db_index=True)
    result = models.CharField(max_length=10, blank=True, default='', db_index=True)
    recorded_at = models.DateTimeField(null=True, blank=True, db_index=True)
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default='')
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'operation_records'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['entity_type', 'serial_number', '-created_at'], name='op_entity_serial_idx'),
            models.Index(fields=['operation_code', '-created_at'], name='op_code_created_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['entity_type', 'serial_number', 'operation_code'],
                condition=models.Q(status='Completed'),
                name='op_entity_serial_code_completed_unique',
            ),
        ]

    def save(self, *args, **kwargs):
        self.serial_number = _normalize_identifier(self.serial_number)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.entity_type}:{self.serial_number} {self.operation_code} {self.status}"


# ── Audit Log ────────────────────────────────────────────────────────────────
# NOTE: AuditLog is defined here so Django can discover it via `get_models()`.
#       All fields are defined in core/audit.py — see that file for details.
class AuditLog(models.Model):
    """Records every mutation (create/update/delete) on MES production data."""

    class AuditAction(models.TextChoices):
        CREATE = 'CREATE', 'Create'
        UPDATE = 'UPDATE', 'Update'
        DELETE = 'DELETE', 'Delete'
        IMPORT = 'IMPORT', 'Bulk Import'

    timestamp   = models.DateTimeField(auto_now_add=True, db_index=True)
    user        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    username    = models.CharField(max_length=150, blank=True, default='')
    action      = models.CharField(max_length=10, choices=AuditAction.choices, db_index=True)
    model_name  = models.CharField(max_length=100, db_index=True)
    object_pk   = models.CharField(max_length=32, db_index=True, blank=True, default='')
    object_repr = models.CharField(max_length=255, blank=True, default='')
    changes     = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp', 'model_name'], name='audit_ts_model_idx'),
            models.Index(fields=['model_name', '-timestamp'], name='audit_model_ts_idx'),
            models.Index(fields=['username', '-timestamp'], name='audit_user_ts_idx'),
        ]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} | {self.username} | {self.action} {self.model_name}({self.object_repr})"


# ── Connect signals (import side-effects) ───────────────────────────────────
from . import signals  # noqa: E402, F401
