from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import RotorBalancing, StatorTestingRecord


class RoleBasedAccessTests(TestCase):
    def make_user(self, role, station=''):
        user = User.objects.create_user(username=f'{role}-{station or "none"}', password='secret')
        user.profile.role = role
        user.profile.station = station
        user.profile.save()
        return user

    def test_operator_only_accesses_assigned_station_page(self):
        user = self.make_user('operator', 'rotor_balancing')
        self.client.force_login(user)

        allowed = self.client.get('/rotor-balancing')
        denied = self.client.get('/stator-testing')

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 302)
        self.assertEqual(denied['Location'], '/rotor-balancing')

    def test_operator_station_page_uses_locked_station_layout(self):
        user = self.make_user('operator', 'rotor_balancing')
        self.client.force_login(user)

        response = self.client.get('/rotor-balancing')

        self.assertTrue(response.context['is_station_mode'])
        self.assertEqual(response.context['base_template'], 'core/base_station.html')
        self.assertContains(response, 'Rotor Balancing')
        self.assertContains(response, 'Current job:')
        self.assertContains(response, 'Station locked')
        self.assertNotContains(response, '<aside')
        self.assertNotContains(response, 'Machines Overview')

    def test_supervisor_station_page_keeps_full_navigation(self):
        user = self.make_user('supervisor')
        self.client.force_login(user)

        response = self.client.get('/rotor-balancing')

        self.assertFalse(response.context['is_station_mode'])
        self.assertEqual(response.context['base_template'], 'core/base.html')
        self.assertContains(response, '<aside')
        self.assertContains(response, 'Machines Overview')

    def test_station_terminal_session_flag_enables_locked_layout(self):
        user = self.make_user('supervisor')
        self.client.force_login(user)
        session = self.client.session
        session['station_terminal'] = True
        session['station'] = 'stator_testing'
        session['current_job'] = 'Job WO-1042'
        session.save()

        response = self.client.get('/stator-testing')

        self.assertTrue(response.context['is_station_mode'])
        self.assertContains(response, 'Stator Testing')
        self.assertContains(response, 'Job WO-1042')
        self.assertNotContains(response, '<aside')

    def test_operator_station_api_is_scoped(self):
        user = self.make_user('operator', 'rotor_balancing')
        RotorBalancing.objects.create(serial_number='R001', result='Pass')
        StatorTestingRecord.objects.create(serial_number='S001', final_result='Pass')
        client = APIClient()
        client.force_authenticate(user=user)

        rotor_response = client.get('/api/rotor-balancing/')
        stator_response = client.get('/api/stator-testing/')

        self.assertEqual(rotor_response.status_code, 200)
        self.assertEqual(stator_response.status_code, 403)

    def test_profile_role_overrides_staff_flags_for_mes_access(self):
        user = User.objects.create_superuser(username='super-operator', password='secret')
        user.profile.role = 'operator'
        user.profile.station = 'laser_marking'
        user.profile.save()
        self.client.force_login(user)

        allowed = self.client.get('/laser-marking')
        denied = self.client.get('/motor-assembly')

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 302)
        self.assertEqual(denied['Location'], '/laser-marking')

    def test_viewer_only_accesses_overview_and_traceability_pages(self):
        user = self.make_user('viewer')
        self.client.force_login(user)

        self.assertEqual(self.client.get('/dashboard').status_code, 200)
        self.assertEqual(self.client.get('/traceability').status_code, 200)
        self.assertEqual(self.client.get('/traceability/motor').status_code, 200)
        self.assertEqual(self.client.get('/rotor-balancing').status_code, 302)
        self.assertEqual(self.client.get('/production-log').status_code, 302)
        self.assertEqual(self.client.get('/add-part').status_code, 302)
        self.assertEqual(self.client.get('/motor-assembly').status_code, 302)

    def test_viewer_can_read_overview_traceability_but_not_write(self):
        user = self.make_user('viewer')
        client = APIClient()
        client.force_authenticate(user=user)

        read_response = client.get('/api/stats')
        station_read_response = client.get('/api/rotor-balancing/')
        write_response = client.post('/api/machines/motor-assembly/', {
            'motor_serial': 'M001',
            'rotor_serial': 'R001',
            'stator_serial': 'S001',
        }, format='json')

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(station_read_response.status_code, 403)
        self.assertEqual(write_response.status_code, 403)

    def test_supervisor_cannot_open_add_part(self):
        user = self.make_user('supervisor')
        self.client.force_login(user)

        response = self.client.get('/add-part')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/dashboard')
