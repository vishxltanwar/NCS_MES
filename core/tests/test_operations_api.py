from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import MotorAssembly, OperationRecord


class OperationsApiRouteTests(TestCase):
    def make_user(self, role, station=''):
        user = User.objects.create_user(username=f'{role}-{station or "none"}', password='secret')
        user.profile.role = role
        user.profile.station = station
        user.profile.save()
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def record_op(self, serial, code, entity_type='rotor'):
        return OperationRecord.objects.create(
            entity_type=entity_type,
            serial_number=serial,
            operation_code=code,
            status='Completed',
        )

    def test_operations_endpoints_require_authentication(self):
        client = APIClient()

        for response in (
            client.get('/api/operations/'),
            client.get('/api/operations/by-serial/rotor/R1/'),
            client.post('/api/operations/record/', {}, format='json'),
            client.post('/api/operations/check-sequence/', {}, format='json'),
        ):
            self.assertIn(response.status_code, (401, 403))

    def test_operator_records_operation_and_reads_it_back(self):
        client = self.client_for(self.make_user('operator', 'rotor_balancing'))
        self.record_op('R1', 'ROTOR_BALANCING')

        created = client.post('/api/operations/record/', {
            'entity_type': 'rotor',
            'serial_number': 'r1',
            'operation_code': 'ROTOR_OP70',
            'result': 'Pass',
        }, format='json')
        by_serial = client.get('/api/operations/by-serial/rotor/R1/')
        listing = client.get('/api/operations/', {'serial': 'R1'})

        self.assertEqual(created.status_code, 201, created.content)
        self.assertIn('ROTOR_OP70', by_serial.json()['completed'])
        self.assertIn('ROTOR_OP80', by_serial.json()['allowed_next'])
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()['results']), 2)

    def test_record_rejects_other_station_operator(self):
        client = self.client_for(self.make_user('operator', 'stator_testing'))

        response = client.post('/api/operations/record/', {
            'entity_type': 'rotor',
            'serial_number': 'R1',
            'operation_code': 'ROTOR_OP70',
        }, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertFalse(OperationRecord.objects.exists())

    def test_record_rejects_missing_prerequisite(self):
        client = self.client_for(self.make_user('admin'))

        response = client.post('/api/operations/record/', {
            'entity_type': 'rotor',
            'serial_number': 'R1',
            'operation_code': 'ROTOR_OP80',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['missing'], ['ROTOR_OP70'])

    def test_check_sequence_reports_missing_prerequisite(self):
        client = self.client_for(self.make_user('operator', 'rotor_balancing'))

        response = client.post('/api/operations/check-sequence/', {
            'entity_type': 'rotor',
            'serial_number': 'R1',
            'operation_code': 'ROTOR_OP70',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'allowed': False, 'missing': ['ROTOR_BALANCING']})

    def test_assign_serial_records_final_motor_serial(self):
        client = self.client_for(self.make_user('operator', 'motor_assembly'))
        link = MotorAssembly.objects.create(motor_serial='M1', rotor_serial='R1', stator_serial='S1')
        self.record_op('M1', 'MOTOR_OP100', entity_type='motor')

        response = client.post(
            f'/api/machines/motor-assembly/{link.pk}/assign-serial/',
            {'final_motor_serial': 'fm1'},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        link.refresh_from_db()
        self.assertEqual(link.final_motor_serial, 'FM1')
        self.assertTrue(OperationRecord.objects.filter(
            serial_number='M1', operation_code='MOTOR_SERIAL_ASSIGN', status='Completed',
        ).exists())
