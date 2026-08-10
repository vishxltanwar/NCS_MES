from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0018_canonical_part_types'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='statortestingrecord',
            name='stator_serial_number_ci_unique',
        ),
        migrations.AlterField(
            model_name='statortestingrecord',
            name='serial_number',
            field=models.CharField(db_index=True, max_length=32),
        ),
    ]
