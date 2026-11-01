from django.test import TestCase
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock

from core.models import MagnetInsertion
from core.rbac import STATION_MAGNET_INSERTION
from core.models import UserProfile
from core.views import _CYCLE_CACHE


class MagnetInsertionCycleTests(TestCase):
    """Simulated PLC value sequence test.

    Cases:
      (a) scan, reset                      -> 0 rows (nothing saved)
      (b) scan, save                       -> 1 row
      (c) same stack again, save           -> 2 rows; lookup by stack_serial returns newer first
    """

    def setUp(self):
        self.user = User.objects.create_user(username='operator', password='pass1234')
        profile = getattr(self.user, 'profile', None)
        if profile is None:
            profile = UserProfile(user=self.user)
        profile.role = 'operator'
        profile.station = STATION_MAGNET_INSERTION
        profile.save()
        # Isolate the in-memory cycle cache between tests.
        _clear = None
        try:
            from core.views import _clear_cycle_cache
            _clear_cycle_cache()
        except Exception:
            pass

    def _headers(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)
        return client

    def test_scan_reset_writes_no_rows(self):
        """Case (a): scan then RESET discards the in-memory cycle; no DB row."""
        # Simulate a scan populating the in-memory cache (both serials present).
        _CYCLE_CACHE['stack_serial'] = 'STACK001'
        _CYCLE_CACHE['magnet_serial'] = 'MAG001'
        _CYCLE_CACHE['start_time'] = None

        client = self._headers()
        resp = client.post('/api/magnet-insertion/reset/', {
            'stack_serial': 'STACK001',
            'magnet_serial': 'MAG001',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()['discarded'])
        self.assertEqual(MagnetInsertion.objects.count(), 0)

    def test_scan_save_creates_one_row(self):
        """Case (b): scan then save creates exactly one DB row."""
        client = self._headers()
        resp = client.post('/api/magnet-insertion/cycle/save/', {
            'stack_serial': 'STACK001',
            'magnet_serial': 'MAG001',
            'pass_fail': True,
            'cycle_time': 45.5,
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertEqual(data['status'], 'OK')
        self.assertTrue(data['pass_fail'])
        self.assertEqual(data['cycle_time'], 45.5)
        self.assertIsNotNone(data['start_time'])
        self.assertIsNotNone(data['end_time'])

        self.assertEqual(MagnetInsertion.objects.count(), 1)
        record = MagnetInsertion.objects.get()
        self.assertEqual(record.stack_serial, 'STACK001')
        self.assertEqual(record.magnet_serial, 'MAG001')
        self.assertEqual(record.status, MagnetInsertion.STATUS_OK)

    def test_double_save_guard_returns_existing_row(self):
        """Saving twice for the same cycle does not create a duplicate."""
        client = self._headers()
        client.post('/api/magnet-insertion/cycle/save/', {
            'stack_serial': 'STACK001', 'magnet_serial': 'MAG001',
            'pass_fail': True, 'cycle_time': 45.5,
        }, format='json')
        resp2 = client.post('/api/magnet-insertion/cycle/save/', {
            'stack_serial': 'STACK001', 'magnet_serial': 'MAG001',
            'pass_fail': True, 'cycle_time': 99.9,
        }, format='json')
        self.assertEqual(resp2.status_code, 200, resp2.content)
        # Still one row; the second call returned the existing row (cycle_time unchanged).
        self.assertEqual(MagnetInsertion.objects.count(), 1)
        record = MagnetInsertion.objects.get()
        self.assertEqual(record.cycle_time, 45.5)

    def test_same_stack_saved_twice_gives_two_rows_newer_first(self):
        """Case (c): same stack_serial saved twice -> 2 rows, latest first."""
        client = self._headers()
        import datetime as dt
        t1 = dt.datetime(2026, 10, 28, 10, 0, 0)
        t2 = dt.datetime(2026, 10, 28, 11, 0, 0)

        client.post('/api/magnet-insertion/cycle/save/', {
            'stack_serial': 'STACK001', 'magnet_serial': 'MAG001',
            'pass_fail': True, 'cycle_time': 45.5,
            'start_time': t1.isoformat(),
        }, format='json')
        client.post('/api/magnet-insertion/cycle/save/', {
            'stack_serial': 'STACK001', 'magnet_serial': 'MAG002',
            'pass_fail': False, 'cycle_time': 50.0,
            'start_time': t2.isoformat(),
        }, format='json')

        self.assertEqual(MagnetInsertion.objects.count(), 2)

        # Default lookup by stack_serial returns the newest cycle first.
        latest = (
            MagnetInsertion.objects
            .filter(stack_serial__iexact='STACK001')
            .order_by('-start_time', '-timestamp')
            .first()
        )
        self.assertEqual(latest.magnet_serial, 'MAG002')
        self.assertFalse(latest.pass_fail)
        self.assertEqual(latest.status, MagnetInsertion.STATUS_NOK)

        # List all cycles of that stack_serial in time order.
        all_cycles = list(
            MagnetInsertion.objects
            .filter(stack_serial__iexact='STACK001')
            .order_by('start_time')
        )
        self.assertEqual(len(all_cycles), 2)
        self.assertEqual(all_cycles[0].magnet_serial, 'MAG001')
        self.assertEqual(all_cycles[1].magnet_serial, 'MAG002')


import datetime as _dt


from unittest.mock import patch


class ModbusStringDecodeTests(TestCase):
    """The FX5U stores the first character of each pair in the low byte."""

    def test_decodes_low_byte_first(self):
        from core.views import _decode_modbus_string
        # Raw D3230 / D3260 words from the register scan (space padded).
        self.assertEqual(
            _decode_modbus_string([21337, 17997, 14388, 18516, 8224, 8224, 8224, 8224, 8224]),
            'YSMF48TH',
        )
        self.assertEqual(
            _decode_modbus_string([12336, 12592, 12337, 18225, 13874, 12336, 12337, 12848, 8224]),
            '0001101G26001002',
        )

    def test_decodes_odd_length_serial(self):
        from core.views import _decode_modbus_string
        # 'NMXF1SH' pads its last word with a space in the high byte.
        self.assertEqual(_decode_modbus_string([0x4D4E, 0x4658, 0x5331, 0x2048]), 'NMXF1SH')


class MagnetInsertionAutoCycleTests(TestCase):
    """Server-side auto-save on the done coil rising edge."""

    def setUp(self):
        self.user = User.objects.create_user(username='autouser', password='pass1234')
        profile = getattr(self.user, 'profile', None)
        if profile is None:
            profile = UserProfile(user=self.user)
        profile.role = 'operator'
        profile.station = STATION_MAGNET_INSERTION
        profile.save()
        try:
            from core.views import _clear_cycle_cache
            _clear_cycle_cache()
        except Exception:
            pass

    def _client(self):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=self.user)
        return c

    def _plc(self, **kw):
        base = {
            'connected': True, 'magnet_serial': '', 'stack_serial': '',
            'state': 1, 'cycle_time_raw': 0,
            'lhs_ok_counter': 0, 'lhs_ng_counter': 0,
        }
        base.update(kw)
        return base

    def _poll(self, client, reading):
        with patch('core.views._read_plc', return_value=reading):
            return client.get('/api/magnet-insertion/status/')

    def _run_cycle(self, client, stack_serial, magnet_serial, ok=True, held_done_polls=0, reset=True, counter=None):
        if counter is None:
            # each run_cycle increments a running global counter
            self._cycle_counter = getattr(self, '_cycle_counter', 0) + 1
            counter = self._cycle_counter
        self._poll(client, self._plc(
            magnet_serial=magnet_serial,
            stack_serial=stack_serial,
            state=1,
            lhs_ok_counter=counter - 1 if ok else counter,
            lhs_ng_counter=counter - 1 if not ok else 0,
        ))
        self._poll(client, self._plc(state=2, cycle_time_raw=100, lhs_ok_counter=counter - 1 if ok else counter, lhs_ng_counter=counter - 1 if not ok else 0))
        self._poll(client, self._plc(state=2, cycle_time_raw=500, lhs_ok_counter=counter - 1 if ok else counter, lhs_ng_counter=counter - 1 if not ok else 0))
        result = self._poll(client, self._plc(state=2, cycle_time_raw=510, lhs_ok_counter=counter if ok else counter - 1, lhs_ng_counter=counter if not ok else 0))
        for _ in range(held_done_polls):
            self._poll(client, self._plc(state=2, cycle_time_raw=510, lhs_ok_counter=counter if ok else counter - 1, lhs_ng_counter=counter if not ok else 0))
        if reset:
            self._poll(client, self._plc(state=1, cycle_time_raw=0, lhs_ok_counter=counter if ok else counter - 1, lhs_ng_counter=counter if not ok else 0))
        return result

    def test_scan_start_done_saves_one_row(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1, lhs_ok_counter=0))
        self._poll(client, self._plc(magnet_serial='', stack_serial='', state=2, cycle_time_raw=0, lhs_ok_counter=0))
        self._poll(client, self._plc(magnet_serial='', stack_serial='', state=2, cycle_time_raw=300, lhs_ok_counter=0))
        r = self._poll(client, self._plc(magnet_serial='', stack_serial='', state=2, cycle_time_raw=510, lhs_ok_counter=1))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body.get('just_saved'), body)
        self.assertEqual(MagnetInsertion.objects.count(), 1)
        rec = MagnetInsertion.objects.get()
        self.assertEqual(rec.stack_serial, 'STACK001')
        self.assertEqual(rec.magnet_serial, 'MAG001')
        self.assertEqual(rec.cycle_time, 51.0)
        self.assertIsNotNone(rec.start_time)
        self.assertIsNotNone(rec.end_time)

    def test_ng_counter_saves_nok(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1, lhs_ng_counter=0))
        self._poll(client, self._plc(state=2, cycle_time_raw=100, lhs_ng_counter=0))
        r = self._poll(client, self._plc(state=2, cycle_time_raw=510, lhs_ng_counter=1))
        self.assertTrue(r.json().get('just_saved'))
        self.assertEqual(MagnetInsertion.objects.count(), 1)
        rec = MagnetInsertion.objects.get()
        self.assertEqual(rec.status, MagnetInsertion.STATUS_NOK)
        self.assertFalse(rec.pass_fail)

    def test_counter_reset_rebaselines_no_save(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1, lhs_ok_counter=0))
        self._poll(client, self._plc(state=2, cycle_time_raw=510, lhs_ok_counter=1))
        self.assertEqual(MagnetInsertion.objects.count(), 1)
        # counter resets to 0
        r = self._poll(client, self._plc(state=1, cycle_time_raw=0, lhs_ok_counter=0))
        self.assertFalse(r.json().get('just_saved'))
        self.assertEqual(MagnetInsertion.objects.count(), 1)

    def test_jump_of_two_logs_missed(self):
        import logging
        with self.assertLogs('core.views', level='INFO') as cm:
            client = self._client()
            self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1, lhs_ok_counter=0))
            self._poll(client, self._plc(state=2, cycle_time_raw=510, lhs_ok_counter=2))
        self.assertEqual(MagnetInsertion.objects.count(), 1)
        self.assertTrue(any('missed' in m for m in cm.output))

    def test_scan_then_reset_writes_no_rows(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1))
        resp = client.post('/api/magnet-insertion/reset/', {
            'stack_serial': 'STACK001', 'magnet_serial': 'MAG001',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()['discarded'])
        self.assertEqual(MagnetInsertion.objects.count(), 0)
        from core.views import _CYCLE_CACHE
        self.assertIsNone(_CYCLE_CACHE['stack_serial'])
        self.assertIsNone(_CYCLE_CACHE['magnet_serial'])

    def test_serial_cleared_at_start_does_not_erase_cache(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1))
        self._poll(client, self._plc(magnet_serial='', stack_serial='', state=2))
        from core.views import _CYCLE_CACHE
        self.assertEqual(_CYCLE_CACHE['magnet_serial'], 'MAG001')
        self.assertEqual(_CYCLE_CACHE['stack_serial'], 'STACK001')

    def test_aborted_cycle_discards_without_save(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1))
        self._poll(client, self._plc(magnet_serial='', stack_serial='', state=2))
        from core.views import _CYCLE_CACHE
        with patch('core.views.PLC_ABORT_GRACE_SECONDS', 0):
            self._poll(client, self._plc(magnet_serial='', stack_serial='', state=1))
        self.assertEqual(MagnetInsertion.objects.count(), 0)
        self.assertIsNone(_CYCLE_CACHE['stack_serial'])

    def test_unsaved_cycle_keeps_serials_during_abort_grace(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1))
        self._poll(client, self._plc(state=2))
        self._poll(client, self._plc(state=1))
        from core.views import _CYCLE_CACHE
        self.assertEqual(_CYCLE_CACHE['stack_serial'], 'STACK001')

    def test_machine_reset_while_idle_clears_scanned_serials(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1))
        with patch('core.views.PLC_ABORT_GRACE_SECONDS', 0):
            r = self._poll(client, self._plc(state=1))

        self.assertIsNone(r.json()['stack_serial'])
        self.assertIsNone(r.json()['magnet_serial'])
        self.assertEqual(MagnetInsertion.objects.count(), 0)

    def test_registers_emptying_just_before_start_keep_serials(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1))
        self._poll(client, self._plc(state=1))
        self._poll(client, self._plc(state=2, cycle_time_raw=510))
        r = self._poll(client, self._plc(state=2, cycle_time_raw=510, lhs_ok_counter=1))

        self.assertTrue(r.json().get('just_saved'), r.content)
        self.assertEqual(MagnetInsertion.objects.get().stack_serial, 'STACK001')

    def test_rescan_after_registers_empty_cancels_clear(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1))
        self._poll(client, self._plc(state=1))
        with patch('core.views.PLC_ABORT_GRACE_SECONDS', 0):
            r = self._poll(client, self._plc(magnet_serial='MAG002', stack_serial='STACK002', state=1))

        self.assertEqual(r.json()['stack_serial'], 'STACK002')
        self.assertEqual(r.json()['magnet_serial'], 'MAG002')

    def test_counter_rising_one_poll_after_state_falls_still_saves(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1))
        self._poll(client, self._plc(state=2, cycle_time_raw=510))
        self._poll(client, self._plc(state=1, cycle_time_raw=510))
        r = self._poll(client, self._plc(state=1, cycle_time_raw=510, lhs_ok_counter=1))

        self.assertTrue(r.json().get('just_saved'), r.content)
        rec = MagnetInsertion.objects.get()
        self.assertEqual(rec.stack_serial, 'STACK001')
        self.assertEqual(rec.magnet_serial, 'MAG001')
        self.assertEqual(rec.cycle_time, 51.0)
        from core.views import _CYCLE_CACHE
        self.assertIsNone(_CYCLE_CACHE['stack_serial'])

    def test_cycle_time_zeroed_when_counter_rises_uses_last_good_value(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1))
        self._poll(client, self._plc(state=2, cycle_time_raw=510))
        r = self._poll(client, self._plc(state=2, cycle_time_raw=0, lhs_ok_counter=1))

        self.assertTrue(r.json().get('just_saved'), r.content)
        self.assertEqual(MagnetInsertion.objects.get().cycle_time, 51.0)

    def test_double_save_guard_on_done_edge(self):
        client = self._client()
        self._poll(client, self._plc(magnet_serial='MAG001', stack_serial='STACK001', state=1, lhs_ok_counter=0))
        self._poll(client, self._plc(magnet_serial='', stack_serial='', state=2, lhs_ok_counter=0))
        r1 = self._poll(client, self._plc(magnet_serial='', stack_serial='', state=2, cycle_time_raw=510, lhs_ok_counter=1))
        self.assertTrue(r1.json()['just_saved'])
        r2 = self._poll(client, self._plc(magnet_serial='', stack_serial='', state=2, cycle_time_raw=510, lhs_ok_counter=1))
        self.assertFalse(r2.json()['just_saved'])
        self.assertEqual(MagnetInsertion.objects.count(), 1)

    def test_back_to_back_cycles_with_different_serials_create_two_rows(self):
        client = self._client()
        self._run_cycle(client, 'STACK001', 'MAG001')
        self._run_cycle(client, 'STACK002', 'MAG002')

        self.assertEqual(MagnetInsertion.objects.count(), 2)
        records = list(MagnetInsertion.objects.order_by('start_time'))
        self.assertEqual(
            [(record.stack_serial, record.magnet_serial) for record in records],
            [('STACK001', 'MAG001'), ('STACK002', 'MAG002')],
        )

    def test_same_serials_in_back_to_back_cycles_create_two_rows(self):
        client = self._client()
        self._run_cycle(client, 'STACK001', 'MAG001')
        self._run_cycle(client, 'STACK001', 'MAG001')

        self.assertEqual(MagnetInsertion.objects.count(), 2)

    def test_done_held_high_for_eight_seconds_creates_one_row(self):
        client = self._client()
        # 27 readings at the configured 300 ms cadence cover the 8-second hold.
        self._run_cycle(client, 'STACK001', 'MAG001', held_done_polls=26, reset=False)

        self.assertEqual(MagnetInsertion.objects.count(), 1)

    def test_scan_and_run_without_done_creates_no_row(self):
        client = self._client()
        self._poll(client, self._plc(
            magnet_serial='MAG001',
            stack_serial='STACK001',
            state=1,
        ))
        for cycle_time_raw in (100, 500, 510):
            self._poll(client, self._plc(state=2, cycle_time_raw=cycle_time_raw))

        self.assertEqual(MagnetInsertion.objects.count(), 0)

    def test_history_list_returns_fields_used_by_table(self):
        client = self._client()
        self._run_cycle(client, 'STACK001', 'MAG001')

        response = client.get('/api/magnet-insertion/')
        self.assertEqual(response.status_code, 200, response.content)
        record = response.json()['results'][0]
        for field in ('status', 'result', 'start_time', 'end_time', 'timestamp'):
            self.assertIn(field, record)
            self.assertTrue(record[field], field)
