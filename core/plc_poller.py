import logging
import threading
import time

from django.db import close_old_connections


logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 0.3

_start_lock = threading.Lock()
_poller_thread = None


def _poll_forever():
    from core.views import _poll_plc

    while True:
        started = time.monotonic()
        close_old_connections()
        try:
            _poll_plc()
        except Exception:
            logger.exception('Background PLC poll failed')
        finally:
            close_old_connections()
        time.sleep(max(0, POLL_INTERVAL_SECONDS - (time.monotonic() - started)))


def start_plc_poller():
    global _poller_thread

    with _start_lock:
        if _poller_thread is not None and _poller_thread.is_alive():
            return
        _poller_thread = threading.Thread(
            target=_poll_forever,
            name='magnet-insertion-plc-poller',
            daemon=True,
        )
        _poller_thread.start()
        logger.info('Started magnet insertion PLC poller at 300 ms intervals')
