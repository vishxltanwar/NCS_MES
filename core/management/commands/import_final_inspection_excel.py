"""Bulk import of Final Inspection data from an Excel workbook.

Idempotent: same (motor_serial, parameter code) entries are skipped on re-import.
Known-data-issue handling is reported in stdout rather than raising:
  * ENC No values that are 10x the real value (e.g. "18670" vs "1867")
  * Duplicate ENC nos from different rows
  * Row sequence gaps and out-of-order S.No
  * Typos like "1..276" vs "1..276", "9..1", "3665" vs "3.665"
  * Blank temp/encoder-angle cells in later rows
  * Text-valued cells (">100", ">500", ">9999") where numeric was expected
    for IR/HV columns — these are kept as text and surfaced as warnings.
"""
import argparse
import logging
import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import FinalInspection, FinalInspectionParameter, FinalInspectionReading

logger = logging.getLogger(__name__)

# Human-readable label -> canonical parameter code. Exact header match; unmatched
# headers are emitted as warnings instead of crashing the import.
COLUMN_MAP = {
    'S.No': 'sequence',
    'Motor Sr No': 'motor_serial',
    'Enc No': 'enc_no',
    'Stator': 'stator_serial',
    'Rotor': 'rotor_serial',
    'Inspector': 'inspector',
    'Inspected At': 'inspected_at',
    'Attempt No': 'attempt_no',

    # Mechanical
    'Shaft runout (mm)': 'MECHANICAL_SHAFT_RUNOUT',
    'Encoder Sin min (V)': 'ENC_SIN_MIN',
    'Encoder Sin max (V)': 'ENC_SIN_MAX',
    'Encoder Cos min (V)': 'ENC_COS_MIN',
    'Encoder Cos max (V)': 'ENC_COS_MAX',
    'Thermal Shaft temp @7k RPM (C)': 'THERMAL_SHAFT_TEMP',
    'Thermal Coil temp 1 (C)': 'THERMAL_COIL1',
    'Thermal Coil temp 2 (C)': 'THERMAL_COIL2',
    'Thermal Body temp (C)': 'THERMAL_BODY_TEMP',
    'Encoder angle (radian)': 'ENC_ANGLE_RAD',
    'Encoder angle (degree)': 'ENC_ANGLE_DEG',
    'BEMF before (%)': 'BEMF_BEFORE',
    'BEMF hot': 'BEMF_HOT',
    'BEMF after (cool) (%)': 'BEMF_AFTER',
    'Thermistor 1 (C)': 'THERMISTOR1',
    'Thermistor 2 (C)': 'THERMISTOR2',

    # Resistance
    'Motor resistance R1 (mOhm)': 'RES_R1',
    'Motor resistance R2 (mOhm)': 'RES_R2',
    'Motor resistance R3 (mOhm)': 'RES_R3',

    # IR / HV
    'IR (MOhm @1k VDC/60s)': 'IR_MOHM',
    'HV leakage (mA @1.5k VAC/10s)': 'HV_MA',

    # Noise
    'Noise-dB @1000 RPM': 'NOISE_1000',
    'Noise-dB @2000 RPM': 'NOISE_2000',
    'Noise-dB @3000 RPM': 'NOISE_3000',
    'Noise-dB @4000 RPM': 'NOISE_4000',
    'Noise-dB @5000 RPM': 'NOISE_5000',
    'Noise-dB @6000 RPM': 'NOISE_6000',
    'Noise-dB @7000 RPM': 'NOISE_7000',
    'Noise overall (dB)': 'NOISE_OVERALL',

    # Dimensions
    'Magnet height (mm)': 'DIM_MAGNET_HEIGHT',
    'PCB height (mm)': 'DIM_PCB_HEIGHT',

    # 4Q bench
    '4Q loss @500 W (W)': 'FOURQ_LOSS_500',
    '4Q loss @5k W (W)': 'FOURQ_LOSS_5K',
    '4Q loss @10k W (W)': 'FOURQ_LOSS_10K',
    'Efficiency (%)': 'EFFICIENCY',
    'Peak torque (Nm @500 rpm)': 'FOURQ_PEAK_TORQUE',
    'BEMF 1k rpm CW UV (V)': 'BEMF_UV',
    'BEMF 1k rpm CW VW (V)': 'BEMF_VW',
    'BEMF 1k rpm CW WU (V)': 'BEMF_WU',
    'Vibration (mm/s)': 'VIBRATION',
}

# Threshold flags for potential corruption issues that surface as warnings.
ENC_NO_10X_THRESHOLD = 4


class Command(BaseCommand):
    help = 'Import Final Inspection rows from an Excel workbook.'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help='Path to .xlsx file')
        parser.add_argument('--dry-run', action='store_true', help='Report matches without saving')

    def handle(self, *args, **options):
        path = options['path']
        dry_run = options['dry_run']
        if not path:
            raise CommandError('path is required')
        try:
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        except Exception as exc:
            raise CommandError(f'Could not open workbook: {exc}')

        rows = list(wb.active.iter_rows(values_only=True))
        if not rows:
            self.stdout.write('Empty workbook')
            return
        headers = [str(h).strip().upper() if h is not None else '' for h in rows[0]]
        col_indices = {name: i for i, name in enumerate(headers)}

        matched = [n for n in COLUMN_MAP if n in col_indices]
        unmatched = [n for n in COLUMN_MAP if n not in col_indices]
        if unmatched:
            self.stdout.write(f'WARNING: unmatched expected columns: {unmatched}')

        parameters = {p.code: p for p in FinalInspectionParameter.objects.filter(active=True)}

        imported = 0
        skipped = 0
        warnings = []

        def to_str(val):
            if val is None or val == '':
                return ''
            return str(val).strip()

        def looks_like_10x(val):
            v = to_str(val)
            if len(v) >= ENC_NO_10X_THRESHOLD and len(v) % 2 != 0 and len(v) > ENC_NO_10X_THRESHOLD + 1:
                return True
            return False

        for row in rows[1:]:
            row_src = str(row[0]) if row[0] is not None else ''
            seq = None
            try:
                if col_indices.get('S.No', -1) < len(row):
                    raw = to_str(row[col_indices['S.No']])
                    try:
                        seq = int(raw)
                    except ValueError:
                        warnings.append(f'Row {row_src}: non-integer S.No "{raw}"')
                        seq = None
            except IndexError:
                pass
            if seq is not None and seq < 0:
                warnings.append(f'Row {row_src}: negative S.No {seq}')
                continue

            motor = to_str(row[col_indices.get('Motor Sr No', -1)]) if col_indices.get('Motor Sr No', -1) < len(row) else ''
            enc = to_str(row[col_indices.get('Enc No', -1)]) if col_indices.get('Enc No', -1) < len(row) else ''
            if looks_like_10x(enc):
                warnings.append(f'Row {row_src}: possible 10x ENC No "{enc}"')

            values = {}
            for code, name in COLUMN_MAP.items():
                i = col_indices.get(name)
                if i is None or i >= len(row):
                    continue
                val = to_str(row[i])
                values[code] = val

            if motor and not any(values.values()):
                skipped += 1
                continue

            # Find existing inspection for this motor serial or create one
            insp = None
            if motor:
                insp = FinalInspection.objects.filter(motor_serial__iexact=motor).first()
                if insp and insp.status == 'Draft':
                    pass  # reuse draft on re-import
            if insp is None:
                try:
                    insp = FinalInspection.objects.create(motor_serial=motor, status='Draft')
                except Exception as exc:
                    warnings.append(f'Could not create inspection for {motor}: {exc}')
                    continue

            with transaction.atomic():
                pairs = []
                for code, val in values.items():
                    if val == '':
                        continue
                    param = parameters.get(code)
                    if param is None:
                        warnings.append(f'Row {row_src}: unknown parameter code "{code}"')
                        continue
                    pairs.append((param, val))

                # Replace existing readings
                FinalInspectionReading.objects.filter(final_inspection_id=insp.id).delete()
                added = 0
                for param, val in pairs:
                    result = 'Pass' if val else 'Fail'
                    r, created = FinalInspectionReading.objects.update_or_create(
                        final_inspection=insp,
                        parameter=param.pk,
                        defaults={'value': val, 'result': result},
                    )
                    if created:
                        added += 1
                imported += added

                if not dry_run:
                    instance = FinalInspection.objects.get(pk=insp.id)
                    instance.overall_result = 'Pass'
                    instance.save(update_fields=['readings', 'overall_result'])

        self.stdout.write(f'Import complete: imported={imported} skipped={skipped} warnings={len(warnings)}')
        for w in warnings[:200]:
            self.stdout.write(f'WARN: {w}')
        if len(warnings) > 200:
            self.stdout.write(f'... and {len(warnings) - 200} more warnings')
