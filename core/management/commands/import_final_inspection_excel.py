"""Import Final Inspection data from the EVR185 tracking workbook.

The source sheet uses a two-row header and has a few known data-entry
problems.  The command never aborts on those problems: it normalises what it
can, records every anomaly in a text report, and stays idempotent by updating
one inspection per motor serial instead of creating duplicates.
"""
import re
from datetime import datetime, time
from pathlib import Path

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.final_inspection_specs import CALCULATED_CODES, PARAMETER_SPECS
from core.models import FinalInspection, FinalInspectionParameter, FinalInspectionReading
from core.views import _spec_check

SHEET_NAME = 'EVR185-motor Data.(tracking)'

COLUMNS = {
    'sequence': 0,
    'motor_serial': 1,
    'enc_no': 2,
    'stator_serial': 3,
    'rotor_serial': 4,
    'magnet_type': 5,
    'pcb_board': 6,
    'MECHANICAL_SHAFT_RUNOUT': 7,
    'MECHANICAL_PARALLELISM': 8,
    'ENC_SIN_MIN': 9,
    'ENC_SIN_MAX': 10,
    'ENC_COS_MIN': 11,
    'ENC_COS_MAX': 12,
    'THERMAL_SHAFT_TEMP': 13,
    'THERMAL_COIL1': 14,
    'THERMAL_COIL2': 15,
    'THERMAL_BODY_TEMP': 16,
    'ENC_ANGLE_RAD': 17,
    'ENC_ANGLE_DEG': 18,
    'ENC_ANGLE_VALUE': 19,
    'BEMF_BEFORE': 20,
    'BEMF_HOT': 21,
    'BEMF_AFTER': 22,
    'THERMISTOR1': 23,
    'THERMISTOR2': 24,
    'THERMISTOR_MISMATCH': 25,
    'RES_R1': 26,
    'RES_R2': 27,
    'RES_R3': 28,
    'IR_MOHM': 29,
    'HV_MA': 30,
    'NOISE_1000': 31,
    'NOISE_2000': 32,
    'NOISE_3000': 33,
    'NOISE_4000': 34,
    'NOISE_5000': 35,
    'NOISE_6000': 36,
    'NOISE_7000': 37,
    'DIM_MAGNET_HEIGHT': 38,
    'DIM_PCB_HEIGHT': 39,
    'FOURQ_LOSS_500': 40,
    'FOURQ_LOSS_5K': 41,
    'FOURQ_LOSS_10K': 42,
    'EFFICIENCY': 43,
    'FOURQ_PEAK_TORQUE': 44,
    'BEMF_UV': 45,
    'BEMF_VW': 46,
    'BEMF_WU': 47,
    'VIBRATION': 48,
}

PARAMETER_CODES = [spec['code'] for spec in PARAMETER_SPECS]
PARAMETER_SPEC_BY_CODE = {spec['code']: spec for spec in PARAMETER_SPECS}
REMARK_INDEXES = (74, 75)
DISPATCH_DATE_INDEX = 70
MOTOR_RE = re.compile(r'01A\w+', re.IGNORECASE)
ENC_TOKEN_RE = re.compile(r'ENC\s*-?\s*(\d+)', re.IGNORECASE)


def _text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _is_motor(value):
    return isinstance(value, str) and bool(MOTOR_RE.search(value))


def _normalise_row(row):
    values = list(row)
    if len(values) > 2 and _is_motor(values[2]) and not _is_motor(values[1]):
        values = values[1:]
    return values


def _cell(row, index):
    return row[index] if 0 <= index < len(row) else None


def _enc_token(motor):
    match = ENC_TOKEN_RE.search(motor or '')
    return match.group(1) if match else ''


def _correct_enc_no(enc, motor, warnings, row_number):
    corrected = enc
    token = _enc_token(motor)
    if enc and token and enc != token:
        if enc.endswith('0') and enc[:-1] == token:
            corrected = token
            warnings.append(f'Row {row_number}: ENC No 10x typo "{enc}" corrected to "{token}"')
        elif enc.lstrip('0') == token:
            corrected = token
            warnings.append(f'Row {row_number}: ENC No "{enc}" corrected to "{token}"')
        else:
            warnings.append(
                f'Row {row_number}: ENC No "{enc}" does not match motor ENC token "{token}"'
            )
    return corrected


def _parse_date(text):
    for fmt in ('%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _within_spec(value, spec_min, spec_max):
    if spec_min is not None and value < spec_min:
        return False
    if spec_max is not None and value > spec_max:
        return False
    return True


def _normalise_value(code, raw, spec, warnings, row_number):
    text = _text(raw)
    if not text:
        return ''
    upper = text.upper()
    if upper in {'#DIV/0!', '#VALUE!', '#N/A', 'NA', 'N/A', '-'}:
        warnings.append(f'Row {row_number}: {code} has placeholder "{text}"')
        return ''
    if text.startswith('>') or text.startswith('<'):
        numeric_text = re.sub(r'[^0-9.\-]', '', text)
        warnings.append(f'Row {row_number}: {code} text limit "{text}" treated as {numeric_text or "blank"}')
        if not numeric_text:
            return ''
        text = numeric_text
    text = re.sub(r'\.{2,}', '.', text).replace(',', '').strip()
    try:
        value = float(text)
    except ValueError:
        warnings.append(f'Row {row_number}: {code} non-numeric value "{text}" ignored')
        return ''

    if code.startswith('BEMF_') and value > 1000:
        warnings.append(f'Row {row_number}: {code} value {text} looks corrupted; left blank')
        return ''

    spec_min = spec.get('spec_min')
    spec_max = spec.get('spec_max')
    if code not in CALCULATED_CODES and value and not _within_spec(value, spec_min, spec_max):
        for factor in (1000, 100, 10):
            candidate = value / factor
            if _within_spec(candidate, spec_min, spec_max):
                warnings.append(
                    f'Row {row_number}: {code} decimal typo "{text}" corrected to {candidate:g}'
                )
                return f'{candidate:.6f}'.rstrip('0').rstrip('.')

    return f'{value:.6f}'.rstrip('0').rstrip('.')


class Command(BaseCommand):
    help = 'Import Final Inspection rows from an EVR185 Excel workbook.'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help='Path to .xlsx file')
        parser.add_argument('--dry-run', action='store_true', help='Report matches without saving')
        parser.add_argument('--sheet', type=str, default=SHEET_NAME, help='Worksheet name')
        parser.add_argument('--report', type=str, default='', help='Anomaly report path')

    def handle(self, *args, **options):
        path = options['path']
        dry_run = options['dry_run']
        if not path:
            raise CommandError('path is required')
        try:
            workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
        except Exception as exc:
            raise CommandError(f'Could not open workbook: {exc}')

        sheet_name = options.get('sheet') or SHEET_NAME
        if sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
        else:
            sheet = workbook.active
            self.stdout.write(f'WARNING: sheet "{sheet_name}" not found; using "{sheet.title}"')

        rows = list(sheet.iter_rows(values_only=True))
        report_option = options.get('report') or ''
        report_path = Path(report_option) if report_option else None
        if not report_path:
            report_path = Path('import_reports') / (Path(path).stem + '.import-report.txt')

        warnings = []
        catalogue = self._catalogue(dry_run)
        seen_enc = {}
        created = 0
        updated = 0
        imported_readings = 0

        for row_number, raw_row in enumerate(rows, start=1):
            row = _normalise_row(raw_row)
            motor = _text(_cell(row, COLUMNS['motor_serial']))
            if not _is_motor(motor):
                continue
            motor = MOTOR_RE.search(motor).group(0).upper()
            enc = _text(_cell(row, COLUMNS['enc_no']))
            enc = _correct_enc_no(enc, _text(_cell(row, COLUMNS['motor_serial'])), warnings, row_number)
            if enc:
                if enc in seen_enc:
                    warnings.append(
                        f'Row {row_number}: duplicate ENC No "{enc}" (first seen row {seen_enc[enc]})'
                    )
                else:
                    seen_enc[enc] = row_number

            values = {}
            for code in PARAMETER_CODES:
                index = COLUMNS.get(code)
                if index is None:
                    continue
                spec = PARAMETER_SPEC_BY_CODE[code]
                value = _normalise_value(code, _cell(row, index), spec, warnings, row_number)
                if value:
                    values[code] = value
                elif code in {
                    'MECHANICAL_SHAFT_RUNOUT', 'ENC_SIN_MIN', 'ENC_SIN_MAX',
                    'ENC_COS_MIN', 'ENC_COS_MAX', 'THERMAL_SHAFT_TEMP',
                    'THERMAL_COIL1', 'THERMAL_COIL2', 'THERMAL_BODY_TEMP',
                    'ENC_ANGLE_RAD', 'ENC_ANGLE_VALUE', 'BEMF_BEFORE',
                    'BEMF_HOT', 'BEMF_AFTER', 'THERMISTOR1', 'THERMISTOR2',
                    'RES_R1', 'RES_R2', 'RES_R3', 'IR_MOHM', 'HV_MA',
                    'DIM_MAGNET_HEIGHT', 'DIM_PCB_HEIGHT', 'FOURQ_LOSS_500',
                    'FOURQ_LOSS_5K', 'FOURQ_LOSS_10K', 'EFFICIENCY',
                    'FOURQ_PEAK_TORQUE',
                }:
                    warnings.append(f'Row {row_number}: {code} is blank')

            self._fill_calculated(values, warnings, row_number)

            remarks = ' | '.join(
                _text(_cell(row, idx)) for idx in REMARK_INDEXES if _text(_cell(row, idx))
            )
            dispatch_date = _parse_date(_text(_cell(row, DISPATCH_DATE_INDEX)))
            header = {
                'assembly_temp_id': '',
                'enc_no': enc,
                'stator_serial': _text(_cell(row, COLUMNS['stator_serial'])),
                'rotor_serial': _text(_cell(row, COLUMNS['rotor_serial'])),
                'magnet_type': _text(_cell(row, COLUMNS['magnet_type'])),
                'pcb_board': _text(_cell(row, COLUMNS['pcb_board'])),
                'remarks': remarks[:255],
            }

            results = {}
            for code, value in values.items():
                spec = catalogue[code]
                results[code] = _spec_check(spec, value)
            overall = 'Fail' if 'Fail' in results.values() else ('Pass' if 'Pass' in results.values() else 'NA')

            if dry_run:
                continue

            with transaction.atomic():
                inspection, was_created = FinalInspection.objects.get_or_create(
                    motor_serial=motor,
                    attempt_no=1,
                    defaults={'status': 'Completed', 'overall_result': overall},
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
                for field, value in header.items():
                    setattr(inspection, field, value)
                inspection.status = 'Completed'
                inspection.overall_result = overall
                if inspection.completed_at is None:
                    inspection.completed_at = timezone.now()
                inspection.save()
                if dispatch_date:
                    inspected_at = timezone.make_aware(datetime.combine(dispatch_date, time.min))
                    FinalInspection.objects.filter(pk=inspection.pk).update(inspected_at=inspected_at)

                inspection.readings.all().delete()
                for code, value in values.items():
                    parameter = catalogue[code]
                    FinalInspectionReading.objects.create(
                        final_inspection=inspection,
                        parameter=parameter,
                        value=value,
                        result=results[code],
                    )
                    imported_readings += 1

        self._write_report(report_path, path, warnings, {
            'created': created,
            'updated': updated,
            'readings': imported_readings,
            'warnings': len(warnings),
            'dry_run': dry_run,
        })
        suffix = ' (dry run)' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'Import complete{suffix}: created={created} updated={updated} '
            f'readings={imported_readings} warnings={len(warnings)}'
        ))
        self.stdout.write(f'Report: {report_path}')
        for warning in warnings[:50]:
            self.stdout.write(f'WARN: {warning}')
        if len(warnings) > 50:
            self.stdout.write(f'... and {len(warnings) - 50} more warnings in the report')

    def _catalogue(self, dry_run):
        catalogue = {}
        for spec in PARAMETER_SPECS:
            if dry_run:
                catalogue[spec['code']] = FinalInspectionParameter(**spec)
                continue
            defaults = {key: value for key, value in spec.items() if key != 'code'}
            parameter, _ = FinalInspectionParameter.objects.get_or_create(
                code=spec['code'], defaults=defaults,
            )
            catalogue[spec['code']] = parameter
        return catalogue

    def _fill_calculated(self, values, warnings, row_number):
        radians = values.get('ENC_ANGLE_RAD')
        if radians:
            try:
                degrees = __import__('math').degrees(float(radians)) % 360
            except ValueError:
                degrees = None
            if degrees is not None:
                values.setdefault('ENC_ANGLE_DEG', f'{degrees:.6f}'.rstrip('0').rstrip('.'))
                values.setdefault('ENC_ANGLE_VALUE', str(int(round(degrees * 10))))
        t1 = values.get('THERMISTOR1')
        t2 = values.get('THERMISTOR2')
        if t1 and t2 and 'THERMISTOR_MISMATCH' not in values:
            try:
                t1_value = float(t1)
                t2_value = float(t2)
            except ValueError:
                return
            if t1_value:
                mismatch = (t2_value - t1_value) / t1_value * 100
                values['THERMISTOR_MISMATCH'] = f'{mismatch:.6f}'.rstrip('0').rstrip('.')
        elif not values.get('THERMISTOR_MISMATCH'):
            warnings.append(f'Row {row_number}: THERMISTOR_MISMATCH could not be calculated')

    def _write_report(self, report_path, source, warnings, summary):
        lines = [
            'Final Inspection Import Report',
            f'Source: {source}',
            f"Mode: {'dry run' if summary['dry_run'] else 'write'}",
            f"Created: {summary['created']}",
            f"Updated: {summary['updated']}",
            f"Readings: {summary['readings']}",
            f"Warnings: {summary['warnings']}",
            '',
        ]
        lines.extend(warnings)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
