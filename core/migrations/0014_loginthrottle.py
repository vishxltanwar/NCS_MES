from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_dailyserialcounter_serial_delivery'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoginThrottle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=80, unique=True)),
                ('failure_count', models.PositiveIntegerField(default=0)),
                ('window_started_at', models.DateTimeField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'login_throttles',
            },
        ),
    ]
