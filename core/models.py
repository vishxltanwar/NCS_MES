# core/models.py
# Napino MES — Django ORM models
from django.db import models


class Serial(models.Model):
    serial_number = models.CharField(max_length=32, unique=True, db_index=True)
    part_number   = models.CharField(max_length=10, default='')
    line_no       = models.CharField(max_length=4, default='')
    shift         = models.CharField(max_length=2, default='')
    part_type     = models.CharField(max_length=20, default='')
    created_at    = models.DateTimeField(auto_now_add=True)
    status        = models.CharField(max_length=20, default='Pending')

    class Meta:
        db_table = 'serials'
        ordering = ['-created_at']

    def __str__(self):
        return self.serial_number


class Part(models.Model):
    serial_number = models.CharField(max_length=32, unique=True, null=True, blank=True, db_index=True)
    part_number   = models.CharField(max_length=10, db_index=True)
    part_name     = models.CharField(max_length=50)
    line_no       = models.CharField(max_length=4)
    shift         = models.CharField(max_length=2)
    created_at    = models.DateTimeField(auto_now_add=True)
    added_by      = models.CharField(max_length=100, default='')

    class Meta:
        db_table = 'parts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.part_name} — {self.part_number}"


class RotorBalancing(models.Model):
    serial_number = models.CharField(max_length=32, unique=True, db_index=True)
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

    def __str__(self):
        return f"{self.serial_number} - {self.result}"
