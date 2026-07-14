from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import MotorAssembly, RotorBalancing, StatorTestingRecord


class MotorAssemblyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='tester', password='secret')
        self.user.profile.role = 'admin'
        self.user.profile.save()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/machines/motor-assembly/'

    def create_rotor(self, serial_number):
        return RotorBalancing.objects.create(serial_number=serial_number, result='Pass')

    def create_stator(self, serial_number):
        return StatorTestingRecord.objects.create(serial_number=serial_number, final_result='Pass')

    def test_create_motor_assembly_link(self):
        self.create_rotor('R001')
        self.create_stator('S001')

        response = self.client.post(self.url, {
            'motor_serial': 'M001',
            'rotor_serial': 'R001',
            'stator_serial': 'S001',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(MotorAssembly.objects.filter(motor_serial='M001').exists())

    def test_create_link_without_motor_master_record(self):
        self.create_rotor('R001')
        self.create_stator('S001')

        response = self.client.post(self.url, {
            'motor_serial': 'M001',
            'rotor_serial': 'R001',
            'stator_serial': 'S001',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(MotorAssembly.objects.filter(motor_serial='M001').exists())

    def test_requires_rotor_and_stator_station_records(self):
        response = self.client.post(self.url, {
            'motor_serial': 'M001',
            'rotor_serial': 'R404',
            'stator_serial': 'S404',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Rotor Sr No not found in rotor balancing records', response.data['errors'])
        self.assertIn('Stator Sr No not found in stator testing records', response.data['errors'])

    def test_blocks_rotor_linked_to_different_motor(self):
        self.create_rotor('R001')
        self.create_stator('S001')
        self.create_stator('S002')
        MotorAssembly.objects.create(motor_serial='M001', rotor_serial='R001', stator_serial='S001')

        response = self.client.post(self.url, {
            'motor_serial': 'M002',
            'rotor_serial': 'R001',
            'stator_serial': 'S002',
        }, format='json')

        self.assertEqual(response.status_code, 409)
        self.assertIn('Rotor Sr No', response.data['detail'])

    def test_blocks_motor_relink_to_different_stator(self):
        self.create_rotor('R001')
        self.create_stator('S001')
        self.create_stator('S002')
        MotorAssembly.objects.create(motor_serial='M001', rotor_serial='R001', stator_serial='S001')

        response = self.client.post(self.url, {
            'motor_serial': 'M001',
            'rotor_serial': 'R001',
            'stator_serial': 'S002',
        }, format='json')

        self.assertEqual(response.status_code, 409)
        self.assertIn('Re-linking is blocked', response.data['detail'])
