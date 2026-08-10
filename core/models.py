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
    part_number   = models.CharField(max_length=10, default='')
    line_no       = models.CharField(max_length=4, default='')
    shift         = models.CharField(max_length=2, default='')
    part_type     = models.CharField(max_length=20, choices=PART_TYPE_CHOICES)
    created_at    = models.DateTimeField(auto_now_add=True)
    status        = models.CharField(max_length=20, default='Pending')
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
    result        = models.CharField(max_length=10, choices=[('Pass', 'Pass'), ('Fail', 'Fail')])
    rotor_type    = models.CharField(max_length=100, null=True, blank=True)
    recorded_at   = models.DateTimeField(null=True, blank=True)
    measure_run   = models.IntegerField(null=True, blank=True)
    balancing_run = models.IntegerField(null=True, blank=True)
    rpm           = models.IntegerField(null=True, blank=True)
    plane1_weight = models.FloatField(null=True, blank=True)
    plane1_degree = models.FloatField(null=True, blank=True)
    plane2_weight = models.FloatField(null=True, blank=True)
    plane2_degree = models.FloatField(null=True, blank=True)
    imported_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rotor_balancing'
        ordering = ['-imported_at']
        indexes = [
            models.Index(fields=['serial_number', 'attempt_no']),
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
    recorded_at = models.DateTimeField(null=True, blank=True)
    final_result = models.CharField(max_length=20)
    
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
    def save(self, *args, **kwargs):
        self.serial_number = _normalize_identifier(self.serial_number)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.final_result}"


class MotorAssembly(models.Model):
    motor_serial = models.CharField(max_length=32, unique=True, db_index=True)
    rotor_serial = models.CharField(max_length=32, unique=True, db_index=True)
    stator_serial = models.CharField(max_length=32, unique=True, db_index=True)
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
