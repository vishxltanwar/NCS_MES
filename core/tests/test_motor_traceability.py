from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
import openpyxl
from rest_framework.test import APIClient

from core.models import MotorAssembly, Part, RotorBalancing, Serial, StatorTestingRecord
from core.views import IST


class MotorTraceabilityApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='tester', password='secret')
        self.user.profile.role = 'admin'
        self.user.profile.save()
        self.client.force_authenticate(user=self.user)

    def create_serial(self, serial_number, part_type):
        return Serial.objects.create(
            serial_number=serial_number,
            part_number='10045',
            line_no='01',
            shift='A',
            part_type=part_type,
        )

    def test_motor_traceability_returns_linked_rotor_and_stator(self):
        self.create_serial('M001', 'Motor')
        MotorAssembly.objects.create(motor_serial='M001', rotor_serial='R001', stator_serial='S001')
        RotorBalancing.objects.create(serial_number='R001', result='Pass', rpm=1200)
        StatorTestingRecord.objects.create(serial_number='S001', final_result='Pass', operator='OP1')

        response = self.client.get('/api/traceability/motor/M001/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['rotor_serial'], 'R001')
        self.assertEqual(response.data['stator_serial'], 'S001')
        self.assertTrue(response.data['rotor_balancing_created'])
        self.assertTrue(response.data['stator_testing_created'])

    def test_motor_traceability_distinguishes_known_motor_without_link(self):
        self.create_serial('M001', 'Motor')

        response = self.client.get('/api/traceability/motor/M001/')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['code'], 'rotor_stator_link_missing')

    def test_motor_traceability_distinguishes_unknown_motor(self):
        response = self.client.get('/api/traceability/motor/M404/')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['code'], 'motor_not_found')

    def test_motor_traceability_accepts_motor_from_parts_master(self):
        Part.objects.create(
            serial_number='PM001',
            part_number='10045',
            part_name='Motor',
            line_no='01',
            shift='A',
        )

        response = self.client.get('/api/traceability/motor/PM001/')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['code'], 'rotor_stator_link_missing')

    def test_station_by_serial_endpoints_return_not_created_statuses(self):
        rotor_response = self.client.get('/api/rotor-balancing/by-serial/R404/')
        stator_response = self.client.get('/api/stator-testing/by-serial/S404/')

        self.assertEqual(rotor_response.status_code, 404)
        self.assertEqual(rotor_response.data['code'], 'rotor_balancing_not_created')
        self.assertEqual(stator_response.status_code, 404)
        self.assertEqual(stator_response.data['code'], 'stator_testing_not_created')

    def test_station_by_serial_endpoints_return_records(self):
        RotorBalancing.objects.create(
            serial_number='R001',
            result='Pass',
            rpm=1200,
            plane1_weight=1.5,
        )
        StatorTestingRecord.objects.create(
            serial_number='S001',
            final_result='Fail',
            ry='1.2',
            hv_result='Pass',
        )

        rotor_response = self.client.get('/api/rotor-balancing/by-serial/R001/')
        stator_response = self.client.get('/api/stator-testing/by-serial/S001/')

        self.assertEqual(rotor_response.status_code, 200)
        self.assertEqual(rotor_response.data['rpm'], 1200)
        self.assertEqual(stator_response.status_code, 200)
        self.assertEqual(stator_response.data['hv_result'], 'Pass')

    def build_rotor_upload(self):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append([
            'dd-mm-yy',
            'hh:mm:ss',
            'Rotor-Type',
            'Rotor-Ident',
            'Mea-Run',
            'Bal-Run',
            'RpM',
            'PL1[G_MM]',
            'PL1[DEG]',
            'PL2[G_MM]',
            'PL2[DEG]',
            'InTol',
        ])
        sheet.append(['20-07-26', '10:00:00', 'Type-A', 'R001', 1, 1, 1200, 12.5, 90, 10.0, 180, 'N'])
        sheet.append(['20-07-26', '10:05:00', 'Type-A', 'R001', 2, 2, 1200, 1.5, 45, 1.0, 90, 'Y'])
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        upload = SimpleUploadedFile(
            'rotor.xlsx',
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        return upload

    def test_rotor_import_stores_multiple_attempts_for_same_serial(self):
        upload = self.build_rotor_upload()
        response = self.client.post('/api/rotor-balancing/import/', {'file': upload}, format='multipart')

        self.assertEqual(response.status_code, 200)
        attempts = RotorBalancing.objects.filter(serial_number='R001').order_by('attempt_no')
        self.assertEqual(attempts.count(), 2)
        self.assertEqual([attempt.attempt_no for attempt in attempts], [1, 2])
        self.assertEqual(attempts[0].result, 'Fail')
        self.assertEqual(attempts[1].result, 'Pass')
        self.assertIsNotNone(attempts[0].recorded_at)
        self.assertIsNotNone(attempts[1].recorded_at)
        first_recorded = attempts[0].recorded_at.astimezone(IST)
        second_recorded = attempts[1].recorded_at.astimezone(IST)
        self.assertEqual(first_recorded.hour, 10)
        self.assertEqual(first_recorded.minute, 0)
        self.assertEqual(second_recorded.hour, 10)
        self.assertEqual(second_recorded.minute, 5)
        self.assertNotEqual(attempts[0].recorded_at, attempts[1].recorded_at)

    def test_rotor_import_backfills_existing_null_recorded_at_attempts(self):
        RotorBalancing.objects.create(serial_number='R001', attempt_no=1, result='Fail')
        RotorBalancing.objects.create(serial_number='R001', attempt_no=2, result='Pass')
        upload = self.build_rotor_upload()

        response = self.client.post('/api/rotor-balancing/import/', {'file': upload}, format='multipart')

        self.assertEqual(response.status_code, 200)
        attempts = RotorBalancing.objects.filter(serial_number='R001').order_by('attempt_no')
        self.assertEqual(attempts.count(), 2)
        self.assertEqual(attempts[0].recorded_at.astimezone(IST).strftime('%H:%M:%S'), '10:00:00')
        self.assertEqual(attempts[1].recorded_at.astimezone(IST).strftime('%H:%M:%S'), '10:05:00')

    def test_rotor_by_serial_returns_latest_attempt_and_history(self):
        RotorBalancing.objects.create(serial_number='R001', attempt_no=1, result='Fail', rpm=1200)
        RotorBalancing.objects.create(serial_number='R001', attempt_no=2, result='Pass', rpm=1300)

        response = self.client.get('/api/rotor-balancing/by-serial/R001/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['attempt_no'], 2)
        self.assertEqual(response.data['latest_attempt'], 2)
        self.assertEqual(response.data['attempt_count'], 2)
        self.assertEqual(response.data['result'], 'Pass')
        self.assertEqual([attempt['attempt_no'] for attempt in response.data['attempts']], [1, 2])
