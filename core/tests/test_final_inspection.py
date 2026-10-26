from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    FinalInspection,
    FinalInspectionParameter,
    FinalInspectionReading,
    OP_FINAL_INSPECTION,
    OperationRecord,
)
from core.views import _calculated_updates, _compute_overall, _spec_check


class ParameterSpecValidationTests(TestCase):
    def setUp(self):
        self.param = FinalInspectionParameter.objects.create(
            code='MECHANICAL_SHAFT_RUNOUT',
            name='Shaft runout',
            section='Mechanical',
            unit='mm',
            spec_min=None,
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

    def test_non_numeric_fails_for_numeric_parameter(self):
        self.assertEqual(_spec_check(self.param, 'Yes'), 'Fail')

    def test_empty_value_is_na(self):
        self.assertEqual(_spec_check(self.param, ''), 'NA')

    def test_no_limits_defaults_pass(self):
        p = FinalInspectionParameter.objects.create(code='NO_LIMITS', name='None', section='Mechanical')
        self.assertEqual(_spec_check(p, 'anything'), 'Pass')
        self.assertEqual(_spec_check(p, ''), 'NA')

    def test_min_only(self):
        p = FinalInspectionParameter.objects.create(
            code='MIN_ONLY', name='Min only', section='Mechanical', spec_min=5, spec_max=None,
        )
        self.assertEqual(_spec_check(p, '3'), 'Fail')
        self.assertEqual(_spec_check(p, '5'), 'Pass')
        self.assertEqual(_spec_check(p, '6'), 'Pass')

    def test_range(self):
        p = FinalInspectionParameter.objects.create(
            code='RANGE_ONLY', name='Range only', section='Motor resistance',
            spec_min=7.35, spec_max=8.45,
        )
        self.assertEqual(_spec_check(p, '7.34'), 'Fail')
        self.assertEqual(_spec_check(p, '7.35'), 'Pass')
        self.assertEqual(_spec_check(p, '8.45'), 'Pass')
        self.assertEqual(_spec_check(p, '8.46'), 'Fail')

    def test_calculated_values_are_computed(self):
        updates = _calculated_updates({
            'ENC_ANGLE_RAD': '4.712',
            'THERMISTOR1': '1.308',
            'THERMISTOR2': '1.255',
        })
        self.assertAlmostEqual(float(updates['ENC_ANGLE_DEG']), 269.942712, places=5)
        self.assertEqual(updates['ENC_ANGLE_VALUE'], '2699')
        self.assertAlmostEqual(float(updates['THERMISTOR_MISMATCH']), -4.051988, places=5)

    def test_calculated_limits_use_computed_value(self):
        p = FinalInspectionParameter.objects.create(
            code='THERMISTOR_MISMATCH', name='Mismatch', section='Thermistor',
            spec_min=-1, spec_max=1, is_calculated=True,
        )
        self.assertEqual(_spec_check(p, '-0.5'), 'Pass')
        self.assertEqual(_spec_check(p, '-4.05'), 'Fail')


class ParameterConstraintTests(TestCase):
    def test_any_null_combination_is_allowed(self):
        FinalInspectionParameter.objects.create(code='BOTH_NULL', name='Both null', section='Mechanical')
        FinalInspectionParameter.objects.create(
            code='MIN_SET', name='Min set', section='Mechanical', spec_min=1,
        )
        FinalInspectionParameter.objects.create(
            code='MAX_SET', name='Max set', section='Mechanical', spec_max=2,
        )
        FinalInspectionParameter.objects.create(
            code='BOTH_SET', name='Both set', section='Mechanical', spec_min=1, spec_max=2,
        )
        self.assertEqual(FinalInspectionParameter.objects.count(), 4)

    def test_min_greater_than_max_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FinalInspectionParameter.objects.create(
                    code='BAD_RANGE', name='Bad range', section='Mechanical',
                    spec_min=3, spec_max=2,
                )


class IncompleteDetectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('inspector', password='secret')
        self.param = FinalInspectionParameter.objects.create(
            code='MECHANICAL_SHAFT_RUNOUT', name='Shaft runout', section='Mechanical', unit='mm',
            spec_min=None,
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
        other = FinalInspectionParameter.objects.exclude(code='MECHANICAL_SHAFT_RUNOUT').filter(active=True)
        for p in other:
            FinalInspectionReading.objects.create(final_inspection=self.insp, parameter=p, value='1.4', result='Pass')
        self.assertEqual(_incomplete_missing(self.insp), [])

    def test_empty_value_counts_as_missing(self):
        from core.views import _incomplete_missing
        reading = FinalInspectionReading.objects.get(final_inspection=self.insp, parameter=self.param)
        reading.value = ''
        reading.result = 'NA'
        reading.save()
        self.assertIn('Shaft runout', _incomplete_missing(self.insp))


class CompleteAndGateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('supervisor', password='secret')
        self.user.profile.role = 'operator'
        self.user.profile.station = 'final_inspection'
        self.user.profile.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.param = FinalInspectionParameter.objects.create(
            code='MECHANICAL_SHAFT_RUNOUT', name='Shaft runout', section='Mechanical', unit='mm',
            spec_min=None,
            spec_max=0.05,
        )
        self.param2 = FinalInspectionParameter.objects.create(
            code='ENC_SIN_MIN', name='Sin min', section='Encoder signals', unit='V',
            spec_min=1.3, spec_max=1.5,
        )
        self.insp = FinalInspection.objects.create(motor_serial='M2', inspector=self.user)
        FinalInspectionReading.objects.create(final_inspection=self.insp, parameter=self.param, value='0.04', result='Pass')
        FinalInspectionReading.objects.create(final_inspection=self.insp, parameter=self.param2, value='1.4', result='Pass')
        self.insp.overall_result = _compute_overall(self.insp)
        self.insp.save(update_fields=['overall_result'])

    def test_complete_marks_completed_and_fires_gate(self):
        resp = self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.assertEqual(resp.status_code, 201)
        self.insp.refresh_from_db()
        self.assertEqual(self.insp.status, 'Completed')
        self.assertEqual(self.insp.overall_result, 'Pass')
        gate = OperationRecord.objects.get(
            entity_type='motor', operation_code=OP_FINAL_INSPECTION, serial_number='M2',
        )
        self.assertEqual(gate.status, 'Completed')
        self.assertEqual(gate.result, 'Pass')

    def test_cannot_complete_with_missing_readings(self):
        FinalInspectionReading.objects.filter(final_inspection=self.insp).delete()
        resp = self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('missing', resp.data)

    def test_cannot_complete_already_completed(self):
        self.insp.status = 'Completed'
        self.insp.overall_result = 'Fail'
        self.insp.remarks = 'Already done'
        self.insp.save()
        response = self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.assertEqual(response.status_code, 409)

    def test_fail_requires_remarks(self):
        reading = FinalInspectionReading.objects.get(final_inspection=self.insp, parameter=self.param)
        reading.value = '0.1'
        reading.result = 'Fail'
        reading.save()
        response = self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.assertEqual(response.status_code, 400)

    def test_fail_when_a_reading_fails(self):
        reading = FinalInspectionReading.objects.get(final_inspection=self.insp, parameter=self.param)
        reading.value = '0.1'
        reading.result = 'Fail'
        reading.save()
        resp = self.client.post(
            f'/api/final-inspection/{self.insp.id}/complete/',
            {'motor_serial': 'M2', 'remarks': 'Out of spec runout'},
        )
        self.assertEqual(resp.status_code, 201)
        self.insp.refresh_from_db()
        self.assertEqual(self.insp.overall_result, 'Fail')
        gate = OperationRecord.objects.get(
            entity_type='motor', operation_code=OP_FINAL_INSPECTION, serial_number='M2',
        )
        self.assertEqual(gate.result, 'Fail')

    def test_no_fail_when_everything_passes(self):
        nl = FinalInspectionParameter.objects.create(
            code='NO_LIMITS_X', name='None', section='Mechanical', is_calculated=False,
        )
        FinalInspectionReading.objects.create(
            final_inspection=self.insp, parameter=nl, value='observed', result='Pass',
        )
        resp = self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.assertEqual(resp.status_code, 201)
        self.insp.refresh_from_db()
        self.assertEqual(self.insp.overall_result, 'Pass')

    def test_viewer_cannot_complete(self):
        viewer = User.objects.create_user('viewer', password='secret')
        viewer.profile.role = 'viewer'
        viewer.profile.save()
        self.client.force_authenticate(user=viewer)
        response = self.client.post(f'/api/final-inspection/{self.insp.id}/complete/', {'motor_serial': 'M2'})
        self.assertEqual(response.status_code, 403)


class SaveDraftApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('final-op', password='secret')
        self.user.profile.role = 'operator'
        self.user.profile.station = 'final_inspection'
        self.user.profile.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        for code, name, section, unit in [
            ('ENC_ANGLE_RAD', 'Encoder angle', 'Encoder angle', 'rad'),
            ('ENC_ANGLE_DEG', 'Encoder angle', 'Encoder angle', 'deg'),
            ('ENC_ANGLE_VALUE', 'Encoder angle value', 'Encoder angle', ''),
            ('THERMISTOR1', 'Thermistor 1', 'Thermistor', 'C'),
            ('THERMISTOR2', 'Thermistor 2', 'Thermistor', 'C'),
            ('THERMISTOR_MISMATCH', 'Mismatch', 'Thermistor', '%'),
        ]:
            FinalInspectionParameter.objects.create(
                code=code, name=name, section=section, unit=unit,
                is_calculated=code in {'ENC_ANGLE_DEG', 'ENC_ANGLE_VALUE', 'THERMISTOR_MISMATCH'},
            )

    def test_save_draft_accepts_partial_readings_and_calculates(self):
        response = self.client.post('/api/final-inspection/', {
            'motor_serial': 'DRAFT-1',
            'assembly_temp_id': 'TEMP-1',
            'enc_no': 'ENC-1',
            'readings': [
                {'parameter': 'ENC_ANGLE_RAD', 'value': '4.712'},
                {'parameter': 'THERMISTOR1', 'value': '1.308'},
                {'parameter': 'THERMISTOR2', 'value': '1.255'},
            ],
        }, format='json')
        self.assertEqual(response.status_code, 201)
        inspection = FinalInspection.objects.get(motor_serial='DRAFT-1')
        self.assertEqual(inspection.assembly_temp_id, 'TEMP-1')
        self.assertEqual(inspection.enc_no, 'ENC-1')
        values = {
            r.parameter.code: r.value
            for r in inspection.readings.select_related('parameter').all()
        }
        self.assertEqual(values['ENC_ANGLE_VALUE'], '2699')
        self.assertAlmostEqual(float(values['ENC_ANGLE_DEG']), 269.942712, places=5)
        self.assertAlmostEqual(float(values['THERMISTOR_MISMATCH']), -4.051988, places=5)

    def test_unknown_parameter_is_rejected(self):
        response = self.client.post('/api/final-inspection/', {
            'motor_serial': 'DRAFT-2',
            'readings': [{'parameter': 'NOT_A_REAL_CODE', 'value': '1'}],
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_attempts_are_separate(self):
        first = self.client.post('/api/final-inspection/', {
            'motor_serial': 'DRAFT-3', 'attempt_no': 1,
        }, format='json')
        second = self.client.post('/api/final-inspection/', {
            'motor_serial': 'DRAFT-3', 'attempt_no': 2,
        }, format='json')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(FinalInspection.objects.filter(motor_serial='DRAFT-3').count(), 2)
