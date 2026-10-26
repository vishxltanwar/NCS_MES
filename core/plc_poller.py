"""Single-connection PLC poller with a shared, latched status snapshot.

The magnet/stack scanner values are written by the PLC as short pulses. The
operator page polls faster than the pulse lifetime, but the PLC also drops
connections when more than one client connects at once (multiple gunicorn
workers and/or multiple browser tabs). This module serializes polling across
processes with a file lock and stores the latched state in a small JSON file so
every worker sees the same snapshot.
"""
from __future__ import annotations

try:
    import fcntl
except ImportError:
    fcntl = None
import json
import logging
import os
import tempfile
import time

from django.conf import settings
from pymodbus.client import ModbusTcpClient

logger = logging.getLogger(__name__)

STATE_PATH = settings.PLC_STATE_PATH
LOCK_PATH = settings.PLC_LOCK_PATH
MIN_POLL_INTERVAL = settings.PLC_POLL_MIN_INTERVAL
STALE_SECONDS = 3.0


def decode_modbus_string(registers):
    if not registers:
        return ""
    # PLC stores one character per byte; each 16-bit register is little-endian.
    return b"".join(
        reg.to_bytes(2, "little") for reg in registers
    ).decode(errors="ignore").strip("\x00").strip()


def _empty_state():
    return {
        'connected': False,
        'magnet_serial': None,
        'stack_serial': None,
        'cycle_complete': False,
        'pass_fail': None,
        'cycle_time': None,
        'cycle_id': 0,
        'raw_magnet': None,
        'raw_stack': None,
        'raw_buffer': None,
        'raw_stack_present': False,
        'suppressed_magnet': None,
        'suppressed_stack': None,
        'debug_values': None,
        'updated_at': 0,
    }


def _read_state():
    try:
        with open(STATE_PATH, 'r', encoding='utf-8') as handle:
            state = json.load(handle)
        if isinstance(state, dict):
            return {**_empty_state(), **state}
    except (OSError, ValueError):
        pass
    return _empty_state()


def _write_state(state):
    state['updated_at'] = time.time()
    directory = os.path.dirname(STATE_PATH) or '.'
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix='.plc-status-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(state, handle)
        os.replace(temp_path, STATE_PATH)
    finally:
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except OSError:
            pass


def _read_register(client, address):
    result = client.read_holding_registers(address=address, count=1, device_id=1)
    if result.isError():
        return None
    return result.registers[0]


def _classify_scanner_buffer(value):
    """Return (magnet, stack) from the generic scanner pulse buffer.

    The PLC copies both scanners' raw values into the same buffer. Magnet QR
    codes are short (e.g. YSMF48TH); stack serials are the 16-character MES
    format. Never guess a stack serial from a short code.
    """
    if not value:
        return None, None
    compact = value.replace(' ', '')
    if len(compact) >= 15:
        return None, value
    if len(compact) >= 4:
        return value, None
    return None, None


def _poll_once(state):
    from core import views as _core_views
    client_cls = getattr(_core_views, 'ModbusTcpClient', ModbusTcpClient)
    client = client_cls(
        settings.PLC_HOST,
        port=settings.PLC_PORT,
        timeout=settings.PLC_TIMEOUT,
    )
    try:
        if not client.connect():
            state['connected'] = False
            state['error'] = 'PLC unavailable'
            return state

        mag_result = client.read_holding_registers(
            address=settings.PLC_MAGNET_SERIAL_REGISTER,
            count=settings.PLC_SERIAL_REGISTER_COUNT,
            device_id=1,
        )
        stack_result = client.read_holding_registers(
            address=settings.PLC_STACK_SERIAL_REGISTER,
            count=settings.PLC_SERIAL_REGISTER_COUNT,
            device_id=1,
        )
        buffer_result = client.read_holding_registers(
            address=settings.PLC_SCANNER_BUFFER_REGISTER,
            count=settings.PLC_SERIAL_REGISTER_COUNT,
            device_id=1,
        )

        raw_magnet = '' if mag_result.isError() else decode_modbus_string(mag_result.registers)
        raw_stack = '' if stack_result.isError() else decode_modbus_string(stack_result.registers)
        raw_buffer = '' if buffer_result.isError() else decode_modbus_string(buffer_result.registers)

        previous_raw_magnet = state.get('raw_magnet')
        previous_raw_stack = state.get('raw_stack')
        if previous_raw_magnet and not raw_magnet:
            state['suppressed_magnet'] = None
        if previous_raw_stack and not raw_stack:
            state['suppressed_stack'] = None

        incoming_magnet = raw_magnet or None
        incoming_stack = raw_stack or None
        buffer_magnet, buffer_stack = _classify_scanner_buffer(raw_buffer)
        if not incoming_magnet and buffer_magnet:
            incoming_magnet = buffer_magnet
        if not incoming_stack and buffer_stack:
            incoming_stack = buffer_stack

        # After a save, the PLC may keep the same scanner value visible for a
        # while. Ignore that held value until it clears; a genuinely new pulse
        # after the clear is processed normally.
        if incoming_magnet and incoming_magnet == state.get('suppressed_magnet'):
            incoming_magnet = None
        if incoming_stack and incoming_stack == state.get('suppressed_stack'):
            incoming_stack = None

        state['connected'] = True
        state.pop('error', None)
        state['raw_magnet'] = raw_magnet or None
        state['raw_stack'] = raw_stack or None
        state['raw_buffer'] = raw_buffer or None

        new_cycle = False
        if incoming_magnet and incoming_magnet != state.get('magnet_serial'):
            # A new magnet QR starts a new cycle. The old stack/result belongs
            # to the previous cycle.
            state['magnet_serial'] = incoming_magnet
            state['stack_serial'] = None
            state['cycle_complete'] = False
            state['pass_fail'] = None
            state['cycle_time'] = None
            state['raw_stack_present'] = False

        if incoming_stack:
            if incoming_stack != state.get('stack_serial'):
                state['stack_serial'] = incoming_stack
                new_cycle = True
            elif not state.get('raw_stack_present'):
                new_cycle = True
            state['cycle_complete'] = True
            state['raw_stack_present'] = True
        else:
            state['raw_stack_present'] = False

        if new_cycle:
            state['cycle_id'] = int(state.get('cycle_id') or 0) + 1

        raw_complete = None
        if settings.PLC_CYCLE_COMPLETE_REGISTER is not None:
            raw_complete = _read_register(client, settings.PLC_CYCLE_COMPLETE_REGISTER)
        if raw_complete is not None:
            if settings.PLC_CYCLE_COMPLETE_BIT is not None:
                complete_now = bool(
                    raw_complete & (1 << settings.PLC_CYCLE_COMPLETE_BIT)
                )
            else:
                complete_now = bool(raw_complete)
            state['cycle_complete'] = bool(state.get('cycle_complete')) or complete_now

        raw_time = None
        if settings.PLC_CYCLE_TIME_REGISTER is not None:
            raw_time = _read_register(client, settings.PLC_CYCLE_TIME_REGISTER)
        raw_result = None
        if settings.PLC_RESULT_REGISTER is not None:
            raw_result = _read_register(client, settings.PLC_RESULT_REGISTER)

        if raw_time is not None:
            cycle_time = round(raw_time * settings.PLC_CYCLE_TIME_SCALE, 2)
            if cycle_time <= 0:
                cycle_time = None
            if cycle_time is not None and (new_cycle or state.get('cycle_time') is None):
                state['cycle_time'] = cycle_time
        if raw_result is not None:
            pass_fail = None
            if (settings.PLC_RESULT_PASS_VALUE is not None
                    and raw_result == settings.PLC_RESULT_PASS_VALUE):
                pass_fail = True
            elif (settings.PLC_RESULT_FAIL_VALUE is not None
                    and raw_result == settings.PLC_RESULT_FAIL_VALUE):
                pass_fail = False
            if pass_fail is not None and (new_cycle or state.get('pass_fail') is None):
                state['pass_fail'] = pass_fail

        state['raw_cycle_complete'] = raw_complete
        state['raw_cycle_time'] = raw_time
        state['raw_result'] = raw_result

        if settings.PLC_DEBUG_REGISTERS:
            low = client.read_holding_registers(address=0, count=11, device_id=1)
            high = client.read_holding_registers(address=3400, count=5, device_id=1)
            debug_values = {
                'low_0_10': None if low.isError() else list(low.registers),
                'high_3400_3404': None if high.isError() else list(high.registers),
            }
            if debug_values != state.get('debug_values'):
                state['debug_values'] = debug_values
                logger.info('PLC debug registers changed: %s', debug_values)

        if not settings.PLC_CYCLE_COMPLETE_REGISTER:
            state['cycle_complete'] = bool(
                state.get('cycle_complete')
                or (state.get('magnet_serial') and state.get('stack_serial'))
            )

        if new_cycle:
            logger.info(
                'PLC new cycle #%s: magnet=%r stack=%r time=%r pass_fail=%r '
                'raw_buffer=%r raw_magnet=%r',
                state.get('cycle_id'), state.get('magnet_serial'),
                state.get('stack_serial'), state.get('cycle_time'),
                state.get('pass_fail'), raw_buffer, raw_magnet,
            )
        return state
    finally:
        try:
            client.close()
        except Exception:
            pass


def get_plc_status():
    """Return the latched PLC snapshot, polling only if the cache is stale."""
    state = _read_state()
    now = time.time()
    if state['updated_at'] and now - state['updated_at'] < MIN_POLL_INTERVAL:
        return state

    if fcntl is None:
        updated = _poll_once(state)
        _write_state(updated)
        return updated

    lock_handle = open(LOCK_PATH, 'a+')
    try:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Another worker/tab is already polling. Serve the shared snapshot.
            return state
        try:
            latest = _read_state()
            if latest['updated_at'] and time.time() - latest['updated_at'] < MIN_POLL_INTERVAL:
                return latest
            updated = _poll_once(latest)
            _write_state(updated)
            return updated
        finally:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
    finally:
        lock_handle.close()


def reset_plc_status():
    """Clear the latched cycle after a record is saved.

    The raw pulse baseline is intentionally kept so the currently visible
    stack value is not treated as a new cycle on the next poll.
    """
    if fcntl is None:
        state = _read_state()
        state['suppressed_magnet'] = state.get('raw_magnet')
        state['suppressed_stack'] = state.get('raw_stack')
        state['magnet_serial'] = None
        state['stack_serial'] = None
        state['cycle_complete'] = False
        state['pass_fail'] = None
        state['cycle_time'] = None
        _write_state(state)
        return

    lock_handle = open(LOCK_PATH, 'a+')
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        state = _read_state()
        state['suppressed_magnet'] = state.get('raw_magnet')
        state['suppressed_stack'] = state.get('raw_stack')
        state['magnet_serial'] = None
        state['stack_serial'] = None
        state['cycle_complete'] = False
        state['pass_fail'] = None
        state['cycle_time'] = None
        _write_state(state)
    finally:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
        finally:
            lock_handle.close()
