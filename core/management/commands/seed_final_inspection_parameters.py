from django.core.management.base import BaseCommand
from django.db import transaction

from core.final_inspection_specs import PARAMETER_SPECS
from core.models import FinalInspectionParameter


class Command(BaseCommand):
    help = 'Create or update the Final Inspection parameter catalogue.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show changes without saving')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        created = 0
        updated = 0
        with transaction.atomic():
            for spec in PARAMETER_SPECS:
                defaults = {key: value for key, value in spec.items() if key != 'code'}
                parameter = FinalInspectionParameter.objects.filter(code=spec['code']).first()
                if parameter is None:
                    created += 1
                    if not dry_run:
                        FinalInspectionParameter.objects.create(**spec)
                    continue
                changed = any(getattr(parameter, key) != value for key, value in defaults.items())
                if changed:
                    updated += 1
                    if not dry_run:
                        for key, value in defaults.items():
                            setattr(parameter, key, value)
                        parameter.save()
        suffix = ' (dry run)' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'Final Inspection parameters: created={created} updated={updated}{suffix}'
        ))
