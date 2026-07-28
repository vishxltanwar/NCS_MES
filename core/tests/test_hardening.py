import base64
import gzip
import json
from datetime import datetime, time
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    DailySerialCounter,
    MagnetInsertion,
    Part,
    RotorBalancing,
    Serial,
    StatorTestingRecord,
)
from core.views import _details_table, _pdf_styles


class HardeningTestMixin:
    def make_user(self, role='admin', station=''):
        user = User.objects.create_user(username=f'{role}-{station or "none"}', password='StrongPass!42')
        user.profile.role = role
        user.profile.station = station
        user.profile.save()
        return user


class SerialGenerationHardeningTests(HardeningTestMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.payload = {
            'part_number': '12345',
            'line_no': '01',
            'shift': 'A',
            'part_type': 'Rotor',
        }

    @patch('core.views.write_to_shared_file')
    def test_deleted_serial_sequence_is_not_reused(self, write_mock):
        first = self.client.post('/api/generate', self.payload, format='json')
        self.assertEqual(first.status_code, 200)
        Serial.objects.get(serial_number=first.data['serial']).delete()

        second = self.client.post('/api/generate', self.payload, format='json')

        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.data['serial'].endswith('001'))
        self.assertTrue(second.data['serial'].endswith('002'))
        self.assertEqual(DailySerialCounter.objects.get(production_date=timezone.localdate()).last_sequence, 2)
        self.assertEqual(write_mock.call_count, 2)

    @patch('core.views.write_to_shared_file', side_effect=OSError('share unavailable'))
    def test_laser_delivery_failure_is_retained_and_reported(self, write_mock):
        response = self.client.post('/api/generate', self.payload, format='json')

        self.assertEqual(response.status_code, 503)
        record = Serial.objects.get(serial_number=response.data['serial'])
        self.assertEqual(record.laser_delivery_status, Serial.LASER_DELIVERY_FAILED)
        self.assertNotEqual(record.laser_delivery_error, '')
        write_mock.assert_called_once_with(record.serial_number)

    @patch('core.views.write_to_shared_file')
    def test_failed_delivery_can_retry_same_reserved_serial(self, write_mock):
        record = Serial.objects.create(
            serial_number='1234501A26209001',
            part_number='12345',
            line_no='01',
            shift='A',
            laser_delivery_status=Serial.LASER_DELIVERY_FAILED,
        )

        response = self.client.post(f'/api/serials/{record.id}/retry-delivery', {}, format='json')

        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.laser_delivery_status, Serial.LASER_DELIVERY_DELIVERED)
        write_mock.assert_called_once_with(record.serial_number)

    def test_database_defaults_support_old_insert_column_set(self):
        with connection.cursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO serials
                    (serial_number, part_number, line_no, shift, part_type, created_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING laser_delivery_status, laser_delivery_error
                ''',
                ['3005101G26209999', '30051', '01', 'G', 'Rotor', timezone.now(), 'Pending'],
            )
            delivery_status, delivery_error = cursor.fetchone()

        self.assertEqual(delivery_status, Serial.LASER_DELIVERY_PENDING)
        self.assertEqual(delivery_error, '')


class CsrfAndAuthenticationHardeningTests(HardeningTestMixin, TestCase):
    def setUp(self):
        self.user = self.make_user('operator', 'laser_marking')

    def test_session_authenticated_write_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.post('/api/mark-done', {'serial': 'missing'}, format='json')

        self.assertEqual(response.status_code, 403)

    def test_login_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)

        response = client.post(
            '/api/login',
            data=json.dumps({'username': self.user.username, 'password': 'StrongPass!42'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(LOGIN_FAILURE_LIMIT=2, LOGIN_FAILURE_WINDOW_SECONDS=60)
    def test_login_is_rate_limited(self):
        client = Client(enforce_csrf_checks=True)
        client.get('/')
        token = client.cookies['csrftoken'].value
        headers = {'HTTP_X_CSRFTOKEN': token}
        body = json.dumps({'username': self.user.username, 'password': 'wrong'})

        self.assertEqual(client.post('/api/login', body, content_type='application/json', **headers).status_code, 401)
        self.assertEqual(client.post('/api/login', body, content_type='application/json', **headers).status_code, 401)
        limited = client.post('/api/login', body, content_type='application/json', **headers)

        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited['Retry-After'], '60')

    def test_scanner_poll_rejects_anonymous_requests(self):
        response = APIClient().get('/api/scanner/poll/')

        self.assertIn(response.status_code, (401, 403))


class ImportAndSeederHardeningTests(HardeningTestMixin, TestCase):
    @override_settings(MAX_IMPORT_FILE_SIZE=16)
    def test_oversized_import_is_rejected_before_parsing(self):
        user = self.make_user('operator', 'rotor_balancing')
        client = APIClient()
        client.force_authenticate(user=user)
        upload = SimpleUploadedFile('records.xlsx', b'x' * 17)

        response = client.post('/api/rotor-balancing/import/', {'file': upload}, format='multipart')

        self.assertEqual(response.status_code, 400)
        self.assertIn('upload limit', response.data['detail'])

    def test_stator_import_preserves_all_surge_error_columns(self):
        user = self.make_user('operator', 'stator_testing')
        client = APIClient()
        client.force_authenticate(user=user)
        headers = [
            'BAR CODE',
            'DATE',
            'FINAL RESULT',
            'SURGE MAIN (R/Y) - ERROR%',
            'SURGE AUX (Y/B) - ERROR%',
            'SURGE MAIN-AUX (B/R) - ERROR%',
        ]
        values = ['STATOR-SURGE-1', '28/07/2026 10:30:00', 'Pass', '1.1', '2.2', '3.3']
        upload = SimpleUploadedFile(
            'records.tsv',
            ('\t'.join(headers) + '\n' + '\t'.join(values)).encode('utf-8'),
        )

        response = client.post('/api/stator-testing/import/', {'file': upload}, format='multipart')

        self.assertEqual(response.status_code, 200)
        record = StatorTestingRecord.objects.get(serial_number='STATOR-SURGE-1')
        self.assertEqual(record.surge_main_ry_error, '1.1')
        self.assertEqual(record.surge_aux_yb_error, '2.2')
        self.assertEqual(record.surge_main_aux_br_error, '3.3')

    def test_stator_import_interprets_naive_timestamp_in_plant_timezone(self):
        user = self.make_user('operator', 'stator_testing')
        client = APIClient()
        client.force_authenticate(user=user)
        upload = SimpleUploadedFile(
            'records.tsv',
            (
                'BAR CODE\tDATE\tFINAL RESULT\n'
                'STATOR-TIME-1\t28/07/2026 10:30:00\tPass'
            ).encode('utf-8'),
        )

        response = client.post('/api/stator-testing/import/', {'file': upload}, format='multipart')

        self.assertEqual(response.status_code, 200)
        recorded_at = timezone.localtime(
            StatorTestingRecord.objects.get(serial_number='STATOR-TIME-1').recorded_at
        )
        self.assertEqual(
            (recorded_at.year, recorded_at.month, recorded_at.day, recorded_at.hour, recorded_at.minute),
            (2026, 7, 28, 10, 30),
        )

    def test_stator_import_reads_real_legacy_xls_workbook(self):
        # Compressed BIFF8 workbook containing BAR CODE, DATE, and FINAL RESULT.
        workbook = gzip.decompress(base64.b64decode(
            'H4sIAD1faGoC/7twXvDBwo1SDxnQgB0DM8O//5wMbEhijEDMCeMIMADl//8HMWE0BxD/HwVDCnByACOSjZVhN+8ZdlAcguL7IQMTwwaWg0CSgeEREMcwFDD45eelKtAROIHdkMgIcoMtkGRkmAMU4WOQBLtKCEwmg0lhMLkerHIPmHQAi/SCSVug2geMUQzn7f20LKCpOIJJCSzHxwAydztYzy2wiCGDKMMJUCqun8AIUcvK4FiUmZgzOCXkWHgYljAA4809NS+1KDHnAYMIMAKXMHz9r8DA8AWWUw8ojIrTV5yRASj+A1WcHYv4ZCYWBoYGhv8J4ATeCkyQv5ghmTA4IzW1xPAPQyg4Q7JBClcnxyAFZ38XV6AmF8cQVx4GBjdPP0cfhSDX4FCfECA3OMQxxD9IN8InWNdQmIHByELfwFzfyMDITMHQwMrYwMrAAKg1ILG4mAtUkoNzvgBKzucF5wgeIJnCwA9mC4LzhQDQ+j8rP17yTQqwjweLNIBLe0idoAryBsN/hkaQDqBmPrAME5gE+UcLzNYGk01gU6XBbCkwKQJMzUBaLUAUynBrBqtpAcuqAe0xBoPL9upIbA0gu/V14A651sf2mkD2OveHVSLrrtsvZFAC1lEpQP0g2Mygw6jDOGsmCOy0h9GM0PLjLpiUxChLOJgEoG7/D634+Bn+MnCBmYJgEsIDhQ4jnMcEDSuQbkYsuhnBupmh6hnBulngPJBuVlC9yyTEsA0cdA5INS8XwygYBaNgFIyCUTAKRsEoGAXUAIzQljqoXQpqjbJCewLs0HGdv0D8b3SYZNiCIIZ8ICwBdkxdGfKAdBFDJUnpR4yBlRFmFiORemDjhSAQDrS9iCGbIQnsjmyS0y+wJ8eI7B+iNQpQLwuRav8/UtxJY/sBDf/zUQAWAAA='
        ))
        user = self.make_user('operator', 'stator_testing')
        client = APIClient()
        client.force_authenticate(user=user)
        upload = SimpleUploadedFile(
            'records.xls',
            workbook,
            content_type='application/vnd.ms-excel',
        )

        response = client.post('/api/stator-testing/import/', {'file': upload}, format='multipart')

        self.assertEqual(response.status_code, 200)
        record = StatorTestingRecord.objects.get(serial_number='STATOR-XLS-1')
        self.assertEqual(record.final_result, 'Pass')

    @patch.dict('os.environ', {}, clear=True)
    def test_seed_command_does_not_create_known_default_user(self):
        stderr = StringIO()

        call_command('seed_users', stderr=stderr)

        self.assertFalse(User.objects.filter(username='vishal.tanwar').exists())
        self.assertIn('MES_SEED_USERNAME', stderr.getvalue())


class TraceabilityImmutabilityTests(HardeningTestMixin, TestCase):
    def test_delete_apis_preserve_production_records(self):
        user = self.make_user('admin')
        client = APIClient()
        client.force_authenticate(user=user)
        records = [
            (Serial.objects.create(serial_number='SERIAL-IMMUTABLE'), '/api/serials/{id}'),
            (
                Part.objects.create(
                    serial_number='PART-IMMUTABLE',
                    part_number='12345',
                    part_name='Rotor',
                    line_no='01',
                    shift='A',
                ),
                '/api/parts/{id}',
            ),
            (
                RotorBalancing.objects.create(serial_number='ROTOR-IMMUTABLE', result='Pass'),
                '/api/rotor-balancing/{id}/',
            ),
            (
                StatorTestingRecord.objects.create(
                    serial_number='STATOR-IMMUTABLE',
                    final_result='Pass',
                ),
                '/api/stator-testing/{id}/',
            ),
            (
                MagnetInsertion.objects.create(
                    stack_serial='STACK-IMMUTABLE',
                    magnet_serial='MAGNET-IMMUTABLE',
                    cycle_time=1.0,
                    pass_fail=True,
                    shift='A',
                ),
                '/api/magnet-insertion/{id}/',
            ),
        ]

        for record, url_template in records:
            with self.subTest(model=record._meta.label):
                response = client.delete(url_template.format(id=record.pk))
                self.assertEqual(response.status_code, 409)
                self.assertTrue(type(record).objects.filter(pk=record.pk).exists())


class MagnetValidationTests(HardeningTestMixin, TestCase):
    def setUp(self):
        self.user = self.make_user('operator', 'magnet_insertion')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/magnet-insertion/create/'

    def test_pass_fail_requires_json_boolean(self):
        response = self.client.post(self.url, {
            'stack_serial': 'STACK-BOOL-1',
            'magnet_serial': 'MAGNET-BOOL-1',
            'cycle_time': 1.2,
            'pass_fail': 'false',
            'shift': 'A',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(MagnetInsertion.objects.filter(stack_serial='STACK-BOOL-1').exists())

    def test_false_boolean_is_stored_as_failure(self):
        response = self.client.post(self.url, {
            'stack_serial': 'STACK-BOOL-2',
            'magnet_serial': 'MAGNET-BOOL-2',
            'cycle_time': 1.2,
            'pass_fail': False,
            'shift': 'A',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertFalse(MagnetInsertion.objects.get(stack_serial='STACK-BOOL-2').pass_fail)

    def test_cycle_time_must_be_finite_and_within_bounds(self):
        invalid_values = (0, -1, 'NaN', 'Infinity', '-Infinity', 3600.01)

        for index, cycle_time in enumerate(invalid_values):
            with self.subTest(cycle_time=cycle_time):
                response = self.client.post(self.url, {
                    'stack_serial': f'STACK-CYCLE-{index}',
                    'magnet_serial': f'MAGNET-CYCLE-{index}',
                    'cycle_time': cycle_time,
                    'pass_fail': True,
                    'shift': 'A',
                }, format='json')

                self.assertEqual(response.status_code, 400)

        self.assertFalse(MagnetInsertion.objects.filter(stack_serial__startswith='STACK-CYCLE-').exists())

    def test_cycle_time_accepts_positive_upper_bound(self):
        response = self.client.post(self.url, {
            'stack_serial': 'STACK-CYCLE-VALID',
            'magnet_serial': 'MAGNET-CYCLE-VALID',
            'cycle_time': 3600,
            'pass_fail': True,
            'shift': 'A',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            MagnetInsertion.objects.get(stack_serial='STACK-CYCLE-VALID').cycle_time,
            3600,
        )


class IdentifierUniquenessTests(HardeningTestMixin, TestCase):
    def test_rotor_attempt_is_case_insensitively_unique_in_database(self):
        RotorBalancing.objects.create(
            serial_number='rotor-race-1',
            attempt_no=1,
            result='Pass',
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            RotorBalancing.objects.create(
                serial_number='ROTOR-RACE-1',
                attempt_no=1,
                result='Fail',
            )

    def test_magnet_pair_is_case_insensitively_unique_in_database(self):
        MagnetInsertion.objects.create(
            stack_serial='stack-race-1',
            magnet_serial='magnet-race-1',
            cycle_time=1,
            pass_fail=True,
            shift='A',
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            MagnetInsertion.objects.create(
                stack_serial='STACK-RACE-1',
                magnet_serial='MAGNET-RACE-1',
                cycle_time=2,
                pass_fail=False,
                shift='A',
            )

    def test_magnet_api_treats_case_variant_as_duplicate(self):
        user = self.make_user('operator', 'magnet_insertion')
        client = APIClient()
        client.force_authenticate(user=user)
        payload = {
            'stack_serial': 'stack-api-1',
            'magnet_serial': 'magnet-api-1',
            'cycle_time': 1,
            'pass_fail': True,
            'shift': 'A',
        }

        first = client.post('/api/magnet-insertion/create/', payload, format='json')
        payload.update(stack_serial='STACK-API-1', magnet_serial='MAGNET-API-1')
        duplicate = client.post('/api/magnet-insertion/create/', payload, format='json')

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.data['duplicate'])
        self.assertEqual(MagnetInsertion.objects.filter(stack_serial='STACK-API-1').count(), 1)


class ProductionLogTimezoneTests(HardeningTestMixin, TestCase):
    def test_daily_aggregation_uses_plant_local_date(self):
        user = self.make_user()
        client = APIClient()
        client.force_authenticate(user=user)
        local_day = timezone.localdate()
        local_created_at = timezone.make_aware(datetime.combine(local_day, time(0, 30)))
        serial = Serial.objects.create(
            serial_number='LOCAL-DATE-1',
            part_number='30051',
            line_no='01',
            shift='A',
            part_type='Rotor',
        )
        Serial.objects.filter(pk=serial.pk).update(created_at=local_created_at)

        response = client.get('/api/production-log')

        self.assertEqual(response.status_code, 200)
        today_bucket = next(row for row in response.data['daily'] if row['date'] == local_day.isoformat())
        self.assertEqual(today_bucket['total'], 1)
        self.assertEqual(today_bucket['A'], 1)


class UiHardeningTests(TestCase):
    def test_pdf_values_are_escaped_before_reportlab_parsing(self):
        table = _details_table([('Operator', '<img src="file:///secret">')], _pdf_styles())
        paragraph = table._cellvalues[0][1]

        self.assertIn('&lt;img', paragraph.text)

    def test_base_template_contains_csrf_and_safe_toast_helpers(self):
        with open('templates/core/base.html', encoding='utf-8') as template:
            content = template.read()

        self.assertIn("headers.set('X-CSRFToken'", content)
        self.assertIn("text.textContent = String(msg ?? '')", content)
        self.assertNotIn('<span>${msg}</span>', content)

    def test_magnet_page_has_manual_process_fallback(self):
        with open('templates/core/magnet_insertion.html', encoding='utf-8') as template:
            content = template.read()

        self.assertIn('manual-cycle-time', content)
        self.assertIn('manual-result', content)
