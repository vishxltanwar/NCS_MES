from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from core.models import FinalInspection, FinalInspectionParameter, FinalInspectionReading, OP_FINAL_INSPECTION
from core.views import _spec_check, _compute_overall


class ParameterSpecValidationTests(TestCase):
    def setUp(self):
        self.param = FinalInspectionParameter.objects.create(
            code='MECHANICAL_SHAFT_RUNOUT',
            name='Shaft runout',
            section='Mechanical',
            unit='mm',
            spec_min=0,
            spec_max=0.05,
            input_type='Float',
        )

    def test_in_spec_passes(self):
        self.assertEqual(_spec_check(self.param, '0.049'), 'Pass')

    def test_at_limit_passes(self):
        self.assertEqual(_spec_check(self.param, '0.05'), 'Pass')

    def test_out_of_spec_fails(self):
        self.assertEqual(_spec_check(self.param, '0.051'), 'Fail')

    def test_negative_values_fail(self):
        self.assertEqual(_spec_check(self.param, '-1'), 'Fail')

    def test_string_yes_passes(self):
        self.assertEqual(_spec_check(self.param, 'Yes'), 'Pass')

    def test_empty_value_fails(self):
        self.assertEqual(_spec_check(self.param, ''), 'Fail')

    def test_no_limits_defaults_pass(self):
        p = FinalInspectionParameter.objects.create(code='NO_LIMITS', name='None', section='Mechanical')
        self.assertEqual(_spec_check(p, 'anything'), 'Pass')

    def test_range_only_min(self):
        p = FinalInspectionParameter.objects.create(code='MIN_ONLY', name='Min only', section='Mechanical', spec_min=5, spec_max=None)
        self.assertEqual(_spec_check(p, '3'), 'Fail')
        self.assertEqual(_spec_check(p, '6'), 'Pass')

    def test_calculated_params_trust_user(self):
        p = FinalInspectionParameter.objects.create(
            code='ENC_ANGLE_RAD', name='Angle rad', section='Encoder signals',
            is_calculated=True, input_type='Text',
            spec_text='Leave blank if filled manually',
        )
        # Any non-empty value passes; empty fails (matches cell-blank handling in import)
        self.assertEqual(_spec_check(p, '3.14159'), 'Pass')
        self.assertEqual(_spec_check(p, ''), 'Fail')


class IncompleteDetectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('inspector', password='secret')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.param = FinalInspectionParameter.objects.create(
            code='MECHANICAL_SHAFT_RUNOUT', name='Shaft runout', section='Mechanical', unit='mm',
            spec_min=0,
            spec_max=0.05,
        )
        self.param2 = FinalInspectionParameter.objects.create(
            code='ENC_SIN_MIN', name='Sin min', section='Encoder signals', unit='V',
            spec_min=1.3, spec_max=1.5,
        )
        self.insp = FinalInspection.objects.create(motor_serial='M1', inspector=self.user)
        FinalInspectionReading.objects.create(final_inspection=self.insp, parameter=self.param, value='0.04', result='Pass')

    def test_missing_required_detected(self):
        from core.views import _incomplete_missing
        missing = _incomplete_missing(self.insp)
        self.assertTrue(any(m == 'Sin min' for m in missing))

    def test_all_filled_no_missing(self):
        from core.views import _incomplete_missing
        other = FinalInspectionParameter.objects.exclude(code__in=['MECHANICAL_SHAFT_RUNOUT']).filter(active=True)
        for p in other:
            FinalInspectionReading.objects.create(final_inspection=self.insp, parameter=p, value='x', result='Pass')
        missing = _incomplete_missing(self.insp)
        self.assertEqual(missing, [])


class CompleteAndGateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('supervisor', password='secret')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.param = FinalInspectionParameter.objects.create(
            code='MECHANICAL_SHAFT_RUNOUT', name='Shaft runout', section='Mechanical', unit='mm',
            spec_min=0,
            spec_max=0.05,
        )
        self.param2 = FinalInspectionParameter.objects.create(
            code='ENC_SIN_MIN', name='Sin min', section='Encoder signals', unit='V',
            spec_min=1.3, spec_max=1.5,
        )
        self.insp = FinalInspection.objects.create(motor_serial='M2', inspector=self.user)
        FinalInspectionReading.objects.create(final_inspection=self.insp, parameter=self.param, value='0.04', result='Pass')
        FinalInspectionReading.objects.create(final_inspection=self.insp, parameter=self.param2, value='1.2', result='Pass')

    def test_complete_marks_completed_and_fires_gate(self):
        resp = self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.assertEqual(resp.status_code, 201)
        self.insp.refresh_from_db()
        self.assertEqual(self.insp.status, 'Completed')
        self.assertEqual(self.insp.overall_result, 'Pass')
        gate = OperationRecord.objects.get(entity_type='motor', operation_code=OP_FINAL_INSPECTION, serial_number='M2')
        self.assertEqual(gate.status, 'Completed')
        self.assertEqual(gate.result, 'Pass')

    def test_cannot_complete_with_missing_readings(self):
        FinalInspectionReading.objects.filter(final_inspection=self.insp).delete()
        resp = self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('missing', resp.data)

    def test_cannot_complete_already_completed(self):
        FinalInspection.objects.create(
            motor_serial='M3', inspector=self.user, status='Completed', overall_result='Fail',
        )
        response = self.client.post('/api/final-inspection/0/complete/', {'motor_serial': 'M3'})
        self.assertEqual(response.status_code, 409)

    def test_no_fail_when_everything_passes(self):
        # Empty value treated as Fail by _spec_check
        # Force a param with no limits so empty → Pass
        from core.models import FinalInspectionParameter
        nl = FinalInspectionParameter.objects.create(
            code='NO_LIMITS_X', name='None', section='Mechanical', is_calculated=False,
        )
        FinalInspectionReading.objects.create(final_inspection=self.insp, parameter=nl, value='', result='Pass')
        self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.insp.refresh_from_db()
        self.assertEqual(self.insp.overall_result, 'Pass')

    def test_fail_when_a_reading_fails(self):
        final_res = FinalInspectionReading.objects.create(
            final_inspection=self.insp, parameter=self.param, value='0.1', result='Fail',
        )
        resp = self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.insp.refresh_from_db()
        self.assertEqual(self.insp.overall_result, 'Fail')
