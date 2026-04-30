# core/management/commands/seed_users.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password


class Command(BaseCommand):
    help = 'Create default user vishal.tanwar with password 12345678'

    def handle(self, *args, **options):
        username = 'vishal.tanwar'
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'User "{username}" already exists — skipping.'))
            return

        User.objects.create(
            username=username,
            first_name='Vishal',
            last_name='Tanwar',
            password=make_password('12345678'),
            is_active=True,
            is_staff=True,
        )
        self.stdout.write(self.style.SUCCESS(f'Created user "{username}" with password 12345678'))
