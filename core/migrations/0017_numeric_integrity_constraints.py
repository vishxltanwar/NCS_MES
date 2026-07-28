from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_magnetinsertion_magnet_stack_pair_ci_unique_and_more'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='rotorbalancing',
            constraint=models.CheckConstraint(
                condition=models.Q(attempt_no__gt=0),
                name='rotor_attempt_number_positive',
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE magnet_insertion '
                        'ADD CONSTRAINT magnet_cycle_time_valid '
                        'CHECK (cycle_time > 0 AND cycle_time <= 3600) NOT VALID'
                    ),
                    reverse_sql=(
                        'ALTER TABLE magnet_insertion '
                        'DROP CONSTRAINT IF EXISTS magnet_cycle_time_valid'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name='magnetinsertion',
                    constraint=models.CheckConstraint(
                        condition=models.Q(cycle_time__gt=0, cycle_time__lte=3600),
                        name='magnet_cycle_time_valid',
                    ),
                ),
            ],
        ),
    ]
