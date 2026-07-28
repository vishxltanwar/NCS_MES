import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create an initial MES administrator from environment-provided credentials'

    def handle(self, *args, **options):
        username = os.getenv('MES_SEED_USERNAME', '').strip()
        password = os.getenv('MES_SEED_PASSWORD', '')
        if not username or not password:
            self.stderr.write(
                self.style.ERROR(
                    'Set MES_SEED_USERNAME and MES_SEED_PASSWORD before running seed_users.'
                )
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'User "{username}" already exists; skipping.'))
            return

        user = User.objects.create_user(
            username=username,
            password=password,
            is_active=True,
            is_staff=True,
        )
        user.profile.role = 'admin'
        user.profile.save(update_fields=['role'])
        self.stdout.write(self.style.SUCCESS(f'Created MES administrator "{username}".'))
