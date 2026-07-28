from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_loginthrottle'),
    ]

    operations = [
        migrations.AlterField(
            model_name='serial',
            name='laser_delivery_error',
            field=models.CharField(blank=True, db_default='', default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='serial',
            name='laser_delivery_status',
            field=models.CharField(
                choices=[('Pending', 'Pending'), ('Delivered', 'Delivered'), ('Failed', 'Failed')],
                db_default='Pending',
                db_index=True,
                default='Pending',
                max_length=12,
            ),
        ),
    ]
