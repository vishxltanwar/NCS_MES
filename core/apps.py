import os
import sys

from django.apps import AppConfig
from django.conf import settings


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        if not settings.PLC_HOST or 'test' in sys.argv:
            return
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true':
            return
        if os.path.basename(sys.argv[0]) == 'manage.py' and 'runserver' not in sys.argv:
            return

        from .plc_poller import start_plc_poller

        start_plc_poller()
