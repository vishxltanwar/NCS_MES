# Generated for role-based access control.

from django.db import migrations, models


def set_staff_profiles_to_admin(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('core', 'UserProfile')
    for user in User.objects.filter(models.Q(is_staff=True) | models.Q(is_superuser=True)):
        profile, _ = UserProfile.objects.get_or_create(user_id=user.id)
        profile.role = 'admin'
        profile.save(update_fields=['role'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('supervisor', 'Supervisor'),
                    ('operator', 'Operator'),
                    ('viewer', 'Viewer'),
                ],
                default='viewer',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='station',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'No station'),
                    ('laser_marking', 'Laser Marking'),
                    ('rotor_balancing', 'Rotor Balancing'),
                    ('stator_testing', 'Stator Testing'),
                    ('magnet_insertion', 'Magnet Insertion'),
                ],
                default='',
                max_length=40,
            ),
        ),
        migrations.RunPython(set_staff_profiles_to_admin, migrations.RunPython.noop),
    ]
