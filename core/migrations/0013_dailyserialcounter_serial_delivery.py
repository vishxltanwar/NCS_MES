from django.db import migrations, models
from django.utils import timezone


def initialize_serial_counters(apps, schema_editor):
    Serial = apps.get_model('core', 'Serial')
    DailySerialCounter = apps.get_model('core', 'DailySerialCounter')
    maximums = {}
    for serial in Serial.objects.exclude(created_at=None).iterator():
        suffix = serial.serial_number[-3:]
        if not suffix.isdigit():
            continue
        production_date = timezone.localtime(serial.created_at).date()
        maximums[production_date] = max(maximums.get(production_date, 0), int(suffix))
    DailySerialCounter.objects.bulk_create([
        DailySerialCounter(production_date=production_date, last_sequence=sequence)
        for production_date, sequence in maximums.items()
    ])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_rotorbalancing_attempt_no'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailySerialCounter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('production_date', models.DateField(unique=True)),
                ('last_sequence', models.PositiveIntegerField(default=0)),
            ],
            options={
                'db_table': 'daily_serial_counters',
                'ordering': ['-production_date'],
            },
        ),
        migrations.RunPython(initialize_serial_counters, migrations.RunPython.noop),
        migrations.AddField(
            model_name='serial',
            name='laser_delivery_error',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='serial',
            name='laser_delivery_status',
            field=models.CharField(
                choices=[('Pending', 'Pending'), ('Delivered', 'Delivered'), ('Failed', 'Failed')],
                db_index=True,
                default='Pending',
                max_length=12,
            ),
        ),
    ]
