from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import MotorAssembly, Part, RotorBalancing, Serial, StatorTestingRecord


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
