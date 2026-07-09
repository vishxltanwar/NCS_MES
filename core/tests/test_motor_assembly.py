from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import MotorAssembly, Part, Serial


class MotorAssemblyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='tester', password='secret')
        self.client.force_authenticate(user=self.user)
        self.url = '/api/machines/motor-assembly/'

    def create_serial(self, serial_number, part_type):
        return Serial.objects.create(
            serial_number=serial_number,
            part_number='10045',
            line_no='01',
            shift='A',
            part_type=part_type,
        )

    def create_part(self, serial_number, part_type):
        return Part.objects.create(
            serial_number=serial_number,
            part_number='10045',
            part_name=part_type,
            line_no='01',
            shift='A',
        )

    def test_create_motor_assembly_link(self):
        self.create_serial('M001', 'Motor')
        self.create_serial('R001', 'Rotor')
        self.create_serial('S001', 'Stator')

        response = self.client.post(self.url, {
            'motor_serial': 'M001',
            'rotor_serial': 'R001',
            'stator_serial': 'S001',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(MotorAssembly.objects.filter(motor_serial='M001').exists())

    def test_create_link_from_parts_master_records(self):
        self.create_part('PM001', 'Motor')
        self.create_part('PR001', 'Rotor')
        self.create_part('PS001', 'Stator')

        response = self.client.post(self.url, {
            'motor_serial': 'PM001',
            'rotor_serial': 'PR001',
            'stator_serial': 'PS001',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(MotorAssembly.objects.filter(motor_serial='PM001').exists())

    def test_blocks_rotor_linked_to_different_motor(self):
        self.create_serial('M001', 'Motor')
        self.create_serial('M002', 'Motor')
        self.create_serial('R001', 'Rotor')
        self.create_serial('S001', 'Stator')
        self.create_serial('S002', 'Stator')
        MotorAssembly.objects.create(motor_serial='M001', rotor_serial='R001', stator_serial='S001')

        response = self.client.post(self.url, {
            'motor_serial': 'M002',
            'rotor_serial': 'R001',
            'stator_serial': 'S002',
        }, format='json')

        self.assertEqual(response.status_code, 409)
        self.assertIn('Rotor Sr No', response.data['detail'])

    def test_blocks_motor_relink_to_different_stator(self):
        self.create_serial('M001', 'Motor')
        self.create_serial('R001', 'Rotor')
        self.create_serial('S001', 'Stator')
        self.create_serial('S002', 'Stator')
        MotorAssembly.objects.create(motor_serial='M001', rotor_serial='R001', stator_serial='S001')

        response = self.client.post(self.url, {
            'motor_serial': 'M001',
            'rotor_serial': 'R001',
            'stator_serial': 'S002',
        }, format='json')

        self.assertEqual(response.status_code, 409)
        self.assertIn('Re-linking is blocked', response.data['detail'])
