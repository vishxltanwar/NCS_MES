# Generated for Motor Details assembly links.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_rename_statorbalancingrecord_statortestingrecord_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='MotorAssembly',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('motor_serial', models.CharField(db_index=True, max_length=32, unique=True)),
                ('rotor_serial', models.CharField(db_index=True, max_length=32, unique=True)),
                ('stator_serial', models.CharField(db_index=True, max_length=32, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'motor assemblies',
                'db_table': 'motor_assembly',
                'ordering': ['-updated_at'],
            },
        ),
    ]
