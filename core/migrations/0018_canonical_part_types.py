from django.db import migrations, models


CANONICAL_PART_TYPES = {
    'rotor': 'Rotor',
    'stator': 'Stator',
    'motor': 'Motor',
}


def canonicalize_part_types(apps, schema_editor):
    Serial = apps.get_model('core', 'Serial')
    Part = apps.get_model('core', 'Part')

    for model, field_name in ((Serial, 'part_type'), (Part, 'part_name')):
        values = model.objects.values_list(field_name, flat=True).distinct()
        for existing_value in values:
            lookup_value = str(existing_value or '').strip().casefold()
            canonical = CANONICAL_PART_TYPES.get(lookup_value)
            if canonical is None:
                raise RuntimeError(
                    f'Cannot canonicalize {model.__name__}.{field_name} value: '
                    f'{existing_value!r}'
                )
            model.objects.filter(**{field_name: existing_value}).update(
                **{field_name: canonical}
            )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0017_numeric_integrity_constraints'),
    ]

    operations = [
        migrations.RunPython(canonicalize_part_types, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='serial',
            name='part_type',
            field=models.CharField(
                choices=[('Rotor', 'Rotor'), ('Stator', 'Stator'), ('Motor', 'Motor')],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='part',
            name='part_name',
            field=models.CharField(
                choices=[('Rotor', 'Rotor'), ('Stator', 'Stator'), ('Motor', 'Motor')],
                max_length=50,
            ),
        ),
        migrations.AddConstraint(
            model_name='serial',
            constraint=models.CheckConstraint(
                condition=models.Q(part_type__in=('Rotor', 'Stator', 'Motor')),
                name='serial_part_type_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='part',
            constraint=models.CheckConstraint(
                condition=models.Q(part_name__in=('Rotor', 'Stator', 'Motor')),
                name='part_name_valid',
            ),
        ),
    ]
