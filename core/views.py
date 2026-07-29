# core/views.py
# Napino MES — All page views + DRF API views
from io import BytesIO
import hashlib
import math
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from django.conf import settings
from django.middleware.csrf import get_token
from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
import logging
import openpyxl
import pandas as pd
import datetime as dt
from django.utils import timezone as django_tz
from pymodbus.client import ModbusTcpClient
import struct
from django.db import DatabaseError, IntegrityError, models, transaction
from django.db.models.functions import Lower, RowNumber
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from utils.scanner import clean_scan_data
from .models import (
    DailySerialCounter,
    LoginThrottle,
    MagnetInsertion,
    MotorAssembly,
    Part,
    RotorBalancing,
    Serial,
    StatorTestingRecord,
)
from .rbac import (
    allowed_pages,
    api_access_required,
    can_access_action,
    first_allowed_url,
    page_access_required,
    user_role,
    user_station,
)

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def csrf_required(view_func):
    """Apply CSRF protection to DRF function views, which are exempt by default."""
    protected = csrf_protect(view_func)
    protected.csrf_exempt = False
    return protected

# ── Shared file path ─────────────────────────────────────────────────────────
def write_to_shared_file(serial: str) -> None:
    if not settings.LASER_SERIAL_FILE:
        raise RuntimeError('LASER_SERIAL_FILE is not configured')
    with open(settings.LASER_SERIAL_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(serial)


# ── Serial generation helper ─────────────────────────────────────────────────
def generate_serial(part_number: str, line_no: str, shift: str, sequence: int) -> str:
    """Build a serial from a sequence that has already been reserved."""
    today = django_tz.localdate()
    yy = today.strftime("%y")
    ddd = today.strftime("%j")
    date_str = f"{yy}{ddd}"
    if sequence > 999:
        raise ValueError("Daily sequence limit of 999 reached for today")
    return f"{part_number}{line_no}{shift}{date_str}{sequence:03d}"


def create_serial_record(part_number: str, line_no: str, shift: str, part_type: str) -> Serial:
    """Reserve a non-reusable daily sequence and persist its serial atomically."""
    today = django_tz.localdate()
    with transaction.atomic():
        used_sequences = []
        for value in Serial.objects.filter(created_at__date=today).values_list('serial_number', flat=True):
            suffix = value[-3:]
            if suffix.isdigit():
                used_sequences.append(int(suffix))
        counter, _ = DailySerialCounter.objects.get_or_create(
            production_date=today,
            defaults={'last_sequence': max(used_sequences, default=0)},
        )
        counter = DailySerialCounter.objects.select_for_update().get(pk=counter.pk)
        sequence = counter.last_sequence + 1
        serial_number = generate_serial(part_number, line_no, shift, sequence)
        counter.last_sequence = sequence
        counter.save(update_fields=['last_sequence'])
        return Serial.objects.create(
            serial_number=serial_number,
            part_number=part_number,
            line_no=line_no,
            shift=shift,
            part_type=part_type,
            laser_delivery_status=Serial.LASER_DELIVERY_PENDING,
        )


def _validate_import_upload(file_obj) -> None:
    if file_obj.size > settings.MAX_IMPORT_FILE_SIZE:
        raise ValueError(
            f'File exceeds the {settings.MAX_IMPORT_FILE_SIZE // (1024 * 1024)} MB upload limit.'
        )

    suffix = Path(file_obj.name or '').suffix.lower()
    if suffix not in {'.xlsx', '.xls', '.csv', '.tsv'}:
        raise ValueError('Unsupported file type. Upload XLSX, XLS, CSV, or TSV.')

    file_obj.seek(0)
    if zipfile.is_zipfile(file_obj):
        file_obj.seek(0)
        with zipfile.ZipFile(file_obj) as archive:
            total_size = sum(member.file_size for member in archive.infolist())
            if total_size > settings.MAX_IMPORT_UNCOMPRESSED_SIZE:
                raise ValueError('Compressed workbook expands beyond the permitted size.')
            for member in archive.infolist():
                if member.compress_size and member.file_size / member.compress_size > 1000:
                    raise ValueError('Workbook contains an unsafe compression ratio.')
    file_obj.seek(0)


def _validate_import_dimensions(row_count: int, column_count: int) -> None:
    if row_count > settings.MAX_IMPORT_ROWS:
        raise ValueError(f'Import exceeds the {settings.MAX_IMPORT_ROWS} row limit.')
    if column_count > settings.MAX_IMPORT_COLUMNS:
        raise ValueError(f'Import exceeds the {settings.MAX_IMPORT_COLUMNS} column limit.')


# ══════════════════════════════════════════════════════════════════════════════
# ── Page View Helpers ─────────────────────────────────────────────────────────

def _request_text(data, field, *, label=None, max_length=None, strip=True, upper=False):
    """Validate text input without coercing structured JSON values."""
    value = data.get(field, '')
    display_name = label or field.replace('_', ' ').capitalize()
    if not isinstance(value, str):
        raise ValueError(f'{display_name} must be text')
    if strip:
        value = value.strip()
    if max_length is not None and len(value) > max_length:
        raise ValueError(f'{display_name} must be no more than {max_length} characters')
    return value.upper() if upper else value


def _render_page(request, template_name, active_page):
    get_token(request)
    user = _user_ctx(request.user)
    return render(request, f'core/{template_name}', {
        'user': user,
        'active_page': active_page,
        'allowed_pages': allowed_pages(request.user),
    })

# ── Page Views ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
def root_view(request):
    if request.user.is_authenticated:
        return redirect(first_allowed_url(request.user) or '/dashboard')
    return render(request, 'core/login.html', {'error': None})


@page_access_required('dashboard')
def dashboard_view(request):
    return _render_page(request, 'dashboard.html', 'dashboard')


@page_access_required('laser')
def laser_marking_view(request):
    return _render_page(request, 'laser_marking.html', 'laser')


@page_access_required('add_part')
def add_part_view(request):
    return _render_page(request, 'add_part.html', 'add_part')


@page_access_required('trace')
def traceability_view(request):
    return _render_page(request, 'traceability.html', 'trace')


@page_access_required('motor_traceability')
def motor_traceability_view(request):
    return _render_page(request, 'motor_traceability.html', 'motor_traceability')


@page_access_required('machine_overview')
def machine_overview_view(request):
    return _render_page(request, 'machine_overview.html', 'machine_overview')


@page_access_required('shift')
def shift_report_view(request):
    return _render_page(request, 'shift_report.html', 'shift')


@page_access_required('production_log')
def production_log_view(request):
    return _render_page(request, 'production_log.html', 'production_log')


@page_access_required('rotor_balancing')
def rotor_balancing_view(request):
    return _render_page(request, 'rotor_balancing.html', 'rotor_balancing')


@page_access_required('stator_testing')
def stator_testing_view(request):
    return _render_page(request, 'stator_testing.html', 'stator_testing')


@page_access_required('magnet_insertion')
def magnet_insertion_view(request):
    return _render_page(request, 'magnet_insertion.html', 'magnet_insertion')


@page_access_required('motor_assembly')
def motor_assembly_view(request):
    return _render_page(request, 'motor_assembly.html', 'motor_assembly')


def _user_ctx(user):
    """Build a user context dict matching the old FastAPI session dict."""
    designation = ''
    if hasattr(user, 'profile'):
        designation = user.profile.designation or ''

    return {
        'username': user.username,
        'full_name': user.get_full_name() or user.username,
        'role': user_role(user),
        'station': user_station(user),
        'designation': designation,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AUTH API
# ══════════════════════════════════════════════════════════════════════════════

def _login_rate_keys(request, username):
    remote_addr = request.META.get('REMOTE_ADDR', '')
    account = username.strip().lower()
    return sorted({
        f'ip:{hashlib.sha256(remote_addr.encode("utf-8")).hexdigest()}',
        f'account:{hashlib.sha256(account.encode("utf-8")).hexdigest()}',
    })


def _login_rate_status(keys):
    now = django_tz.now()
    window = timedelta(seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS)
    limited = False
    with transaction.atomic():
        for key in keys:
            throttle, _ = LoginThrottle.objects.get_or_create(
                key=key,
                defaults={'window_started_at': now},
            )
            throttle = LoginThrottle.objects.select_for_update().get(pk=throttle.pk)
            if now - throttle.window_started_at >= window:
                throttle.failure_count = 0
                throttle.window_started_at = now
                throttle.save(update_fields=['failure_count', 'window_started_at', 'updated_at'])
            limited = limited or throttle.failure_count >= settings.LOGIN_FAILURE_LIMIT
    return limited


def _record_login_failure(keys):
    now = django_tz.now()
    window = timedelta(seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS)
    with transaction.atomic():
        for key in keys:
            throttle, _ = LoginThrottle.objects.get_or_create(
                key=key,
                defaults={'window_started_at': now},
            )
            throttle = LoginThrottle.objects.select_for_update().get(pk=throttle.pk)
            if now - throttle.window_started_at >= window:
                throttle.failure_count = 0
                throttle.window_started_at = now
            throttle.failure_count += 1
            throttle.save(update_fields=['failure_count', 'window_started_at', 'updated_at'])


@csrf_required
@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    try:
        username = _request_text(request.data, 'username', max_length=150)
        password = _request_text(request.data, 'password', max_length=4096, strip=False)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    rate_keys = _login_rate_keys(request, username)
    if _login_rate_status(rate_keys):
        response = Response(
            {'detail': 'Too many failed sign-in attempts. Try again later.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        response['Retry-After'] = str(settings.LOGIN_FAILURE_WINDOW_SECONDS)
        return response

    user = authenticate(request, username=username, password=password)
    if user is None:
        _record_login_failure(rate_keys)
        return Response({'detail': 'Invalid username or password'}, status=status.HTTP_401_UNAUTHORIZED)

    account_key = next(key for key in rate_keys if key.startswith('account:'))
    LoginThrottle.objects.filter(key=account_key).delete()
    login(request, user)
    full_name = user.get_full_name() or user.username
    return Response({
        'status': 'ok',
        'full_name': full_name,
        'next_url': first_allowed_url(user) or '/dashboard',
    })


@csrf_required
@api_view(['POST'])
def api_logout(request):
    logout(request)
    return Response({'status': 'logged out'})


# ══════════════════════════════════════════════════════════════════════════════
# SERIAL API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['POST'])
@api_access_required('laser_write')
def api_generate(request):
    try:
        part_number = _request_text(request.data, 'part_number', label='Part number', max_length=5)
        line_no = _request_text(request.data, 'line_no', label='Line number', max_length=2)
        shift_val = _request_text(request.data, 'shift', max_length=1, upper=True)
        part_type = _request_text(request.data, 'part_type', label='Part type', max_length=20)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)

    if not part_number.isdigit() or len(part_number) != 5:
        return Response({'detail': 'Part number must be exactly 5 digits'}, status=400)
    if not line_no.isdigit() or len(line_no) != 2:
        return Response({'detail': 'Line number must be 2 digits (e.g. 01)'}, status=400)
    if shift_val not in ('A', 'B', 'C', 'G'):
        return Response({'detail': 'Shift must be A, B, C, or G'}, status=400)

    try:
        entry = create_serial_record(
            part_number,
            line_no,
            shift_val,
            part_type or '',
        )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    except (IntegrityError, DatabaseError):
        logger.exception('Unable to reserve and persist a laser serial')
        return Response({'detail': 'Unable to create serial record'}, status=500)

    try:
        write_to_shared_file(entry.serial_number)
    except OSError as exc:
        logger.exception('Unable to deliver serial %s to the laser share', entry.serial_number)
        entry.laser_delivery_status = Serial.LASER_DELIVERY_FAILED
        entry.laser_delivery_error = str(exc)[:255]
        entry.save(update_fields=['laser_delivery_status', 'laser_delivery_error'])
        return Response({
            'serial': entry.serial_number,
            'status': 'delivery_failed',
            'detail': 'Serial was reserved but could not be delivered to the laser machine.',
        }, status=503)

    entry.laser_delivery_status = Serial.LASER_DELIVERY_DELIVERED
    entry.laser_delivery_error = ''
    entry.save(update_fields=['laser_delivery_status', 'laser_delivery_error'])
    return Response({'serial': entry.serial_number, 'status': 'success'})


@api_view(['GET'])
@api_access_required('serials_read')
def api_serials(request):
    latest_rotor_result = RotorBalancing.objects.filter(
        serial_number__iexact=models.OuterRef('serial_number')
    ).order_by(
        '-attempt_no',
        '-recorded_at',
        '-imported_at',
    ).values('result')[:1]
    serials = Serial.objects.annotate(
        latest_rotor_result=models.Subquery(latest_rotor_result)
    ).order_by('-created_at')[:100]
    data = []
    serial_numbers_seen = set()
    
    for s in serials:
        serial_numbers_seen.add(s.serial_number)
        data.append({
            'id': s.id,
            'serial_number': s.serial_number,
            'part_number': s.part_number,
            'line_no': s.line_no,
            'shift': s.shift,
            'part_type': s.part_type or '',
            'created_at': s.created_at.astimezone(IST).isoformat() if s.created_at else '—',
            'status': s.status,
            'laser_delivery_status': s.laser_delivery_status,
            'rotor_result': s.latest_rotor_result,
        })
        
    # Append isolated Rotor Balancing records
    serial_keys_seen = {serial.lower() for serial in serial_numbers_seen}
    isolated_rotors = RotorBalancing.objects.annotate(
        serial_key=Lower('serial_number'),
        serial_rank=models.Window(
            expression=RowNumber(),
            partition_by=[Lower('serial_number')],
            order_by=[
                models.F('attempt_no').desc(),
                models.F('recorded_at').desc(nulls_last=True),
                models.F('imported_at').desc(),
            ],
        ),
    ).exclude(
        serial_key__in=serial_keys_seen
    ).filter(
        serial_rank=1
    ).order_by('-imported_at')[:50]
    for r in isolated_rotors:
        data.append({
            'id': f'rbm-{r.id}',
            'serial_number': r.serial_number,
            'part_number': 'N/A',
            'line_no': 'N/A', # not stored anymore
            'shift': 'N/A', # not stored anymore
            'part_type': r.rotor_type or 'Rotor',
            'created_at': r.recorded_at.astimezone(IST).isoformat() if r.recorded_at else (r.imported_at.astimezone(IST).isoformat() if r.imported_at else '—'),
            'status': 'Imported',
            'laser_delivery_status': 'N/A',
            'rotor_result': r.result
        })
        
    return Response(data)


@api_view(['DELETE'])
@api_access_required('serial_delete')
def api_delete_serial(request, serial_id):
    try:
        Serial.objects.get(id=serial_id)
    except Serial.DoesNotExist:
        return Response({'detail': 'Serial not found'}, status=404)
    return Response({
        'detail': 'Production traceability records are immutable and cannot be deleted.'
    }, status=409)


@api_view(['POST'])
@api_access_required('laser_write')
def api_retry_serial_delivery(request, serial_id):
    try:
        entry = Serial.objects.get(id=serial_id)
    except Serial.DoesNotExist:
        return Response({'detail': 'Serial not found'}, status=404)

    try:
        write_to_shared_file(entry.serial_number)
    except OSError as exc:
        logger.exception('Unable to retry delivery for serial %s', entry.serial_number)
        entry.laser_delivery_status = Serial.LASER_DELIVERY_FAILED
        entry.laser_delivery_error = str(exc)[:255]
        entry.save(update_fields=['laser_delivery_status', 'laser_delivery_error'])
        return Response({
            'serial': entry.serial_number,
            'status': 'delivery_failed',
            'detail': 'Serial could not be delivered to the laser machine.',
        }, status=503)

    entry.laser_delivery_status = Serial.LASER_DELIVERY_DELIVERED
    entry.laser_delivery_error = ''
    entry.save(update_fields=['laser_delivery_status', 'laser_delivery_error'])
    return Response({'serial': entry.serial_number, 'status': 'delivered'})


@api_view(['POST'])
@api_access_required('mark_done')
def api_mark_done(request):
    try:
        serial = _request_text(request.data, 'serial', max_length=32, upper=True)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    if not serial:
        return Response({'detail': 'Serial is required'}, status=400)
    try:
        entry = Serial.objects.get(serial_number__iexact=serial)
    except Serial.DoesNotExist:
        return Response({'detail': 'Serial not found'}, status=404)

    entry.status = 'Marked'
    entry.save(update_fields=['status'])
    return Response({'serial': entry.serial_number, 'status': 'Marked'})


def _current_shift_metrics(now):
    plant_timezone = django_tz.get_current_timezone()
    local_now = django_tz.localtime(now, plant_timezone)
    shift_specs = (
        ('G', 'General', dt.time(8, 30), dt.time(17, 0)),
        ('A', 'Morning', dt.time(6, 30), dt.time(15, 0)),
        ('B', 'Afternoon', dt.time(15, 0), dt.time(23, 30)),
        ('C', 'Night', dt.time(23, 30), dt.time(6, 30)),
    )
    for shift_id, name, start_time, end_time in shift_specs:
        if start_time < end_time:
            active = start_time <= local_now.time() < end_time
        else:
            active = local_now.time() >= start_time or local_now.time() < end_time
        if not active:
            continue

        start_day = local_now.date()
        end_day = local_now.date()
        if start_time >= end_time:
            if local_now.time() < end_time:
                start_day -= timedelta(days=1)
            else:
                end_day += timedelta(days=1)
        start_at = django_tz.make_aware(datetime.combine(start_day, start_time), plant_timezone)
        end_at = django_tz.make_aware(datetime.combine(end_day, end_time), plant_timezone)
        total_seconds = (end_at - start_at).total_seconds()
        elapsed_seconds = max(0, min(total_seconds, (local_now - start_at).total_seconds()))
        remaining_minutes = max(0, int((total_seconds - elapsed_seconds + 59) // 60))
        return {
            'id': shift_id,
            'name': name,
            'start_at': start_at,
            'end_at': end_at,
            'progress_pct': round((elapsed_seconds / total_seconds) * 100),
            'remaining_minutes': remaining_minutes,
        }

    raise RuntimeError('Shift schedule does not cover the current time')


@api_view(['GET'])
@api_access_required('stats')
def api_stats(request):
    now = django_tz.now()
    current_shift = _current_shift_metrics(now)
    today = django_tz.localtime(now).date()
    total_today = Serial.objects.filter(created_at__date=today).count()
    marked_today = Serial.objects.filter(created_at__date=today, status='Marked').count()
    pending_today = Serial.objects.filter(created_at__date=today, status='Pending').count()
    total_all = Serial.objects.count()
    
    rotor_today_objs = RotorBalancing.objects.filter(imported_at__date=today)
    rotor_total = rotor_today_objs.count()
    rotor_pass = rotor_today_objs.filter(result='Pass').count()
    rotor_fail = rotor_today_objs.filter(result='Fail').count()
    
    stator_today_objs = StatorTestingRecord.objects.filter(imported_at__date=today)
    stator_total = stator_today_objs.count()
    stator_pass = stator_today_objs.filter(final_result__iexact='Pass').count()
    stator_fail = stator_today_objs.filter(final_result__iexact='Fail').count()

    magnet_today_objs = MagnetInsertion.objects.filter(timestamp__date=today)
    magnet_total = magnet_today_objs.count()
    magnet_pass = magnet_today_objs.filter(pass_fail=True).count()
    magnet_fail = magnet_today_objs.filter(pass_fail=False).count()
    live_rate = Serial.objects.filter(
        created_at__gt=now - timedelta(hours=1),
        created_at__lte=now,
    ).count()
    current_shift_count = Serial.objects.filter(
        created_at__gte=current_shift['start_at'],
        created_at__lt=current_shift['end_at'],
    ).count()
    
    return Response({
        'total_today': total_today,
        'marked_today': marked_today,
        'pending_today': pending_today,
        'total_all': total_all,
        'rotor_total': rotor_total,
        'rotor_pass': rotor_pass,
        'rotor_fail': rotor_fail,
        'stator_total': stator_total,
        'stator_pass': stator_pass,
        'stator_fail': stator_fail,
        'magnet_total': magnet_total,
        'magnet_pass': magnet_pass,
        'magnet_fail': magnet_fail,
        'live_rate': live_rate,
        'current_shift': {
            'id': current_shift['id'],
            'name': current_shift['name'],
            'start': current_shift['start_at'].isoformat(),
            'end': current_shift['end_at'].isoformat(),
            'progress_pct': current_shift['progress_pct'],
            'remaining_minutes': current_shift['remaining_minutes'],
            'count': current_shift_count,
        },
    })


def _rotor_balancing_payload(r):
    return {
        'id': r.id,
        'serial_number': r.serial_number,
        'attempt_no': r.attempt_no,
        'result': r.result,
        'rotor_type': r.rotor_type or '',
        'measure_run': r.measure_run if r.measure_run is not None else '',
        'balancing_run': r.balancing_run if r.balancing_run is not None else '',
        'rpm': r.rpm if r.rpm is not None else '',
        'plane1_weight': r.plane1_weight if r.plane1_weight is not None else '',
        'plane1_degree': r.plane1_degree if r.plane1_degree is not None else '',
        'plane2_weight': r.plane2_weight if r.plane2_weight is not None else '',
        'plane2_degree': r.plane2_degree if r.plane2_degree is not None else '',
        'recorded_at': r.recorded_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if r.recorded_at else '',
        'imported_at': r.imported_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if r.imported_at else '',
    }


def _latest_rotor_balancing(serial):
    return RotorBalancing.objects.filter(serial_number__iexact=serial).order_by(
        '-attempt_no',
        '-recorded_at',
        '-imported_at',
    ).first()


def _rotor_balancing_history_payload(serial):
    attempts = RotorBalancing.objects.filter(serial_number__iexact=serial).order_by('attempt_no', 'recorded_at', 'imported_at')
    return [_rotor_balancing_payload(attempt) for attempt in attempts]


def _stator_testing_payload(r):
    return {
        'id': r.id,
        'serial_number': r.serial_number,
        'recorded_at': r.recorded_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if r.recorded_at else '',
        'final_result': r.final_result,
        'operator': r.operator,
        'code_number': r.code_number,
        'symmetry': r.symmetry,
        'ry': r.ry,
        'ry_result': r.ry_result,
        'yb': r.yb,
        'yb_result': r.yb_result,
        'br': r.br,
        'br_result': r.br_result,
        'thd_win': r.thd_win,
        'thd_result': r.thd_result,
        'ir_m_ohms': r.ir_m_ohms,
        'ir_result': r.ir_result,
        'high_voltage': r.high_voltage,
        'hv_result': r.hv_result,
        'surge_voltage': r.surge_voltage,
        'surge_main_ry_error': r.surge_main_ry_error,
        'surge_ry_result': r.surge_ry_result,
        'surge_aux_yb_error': r.surge_aux_yb_error,
        'surge_aux_yb_result': r.surge_aux_yb_result,
        'surge_main_aux_br_error': r.surge_main_aux_br_error,
        'surge_main_aux_br_result': r.surge_main_aux_br_result,
        'inductance_1': r.inductance_1,
        'l1_result': r.l1_result,
        'inductance_2': r.inductance_2,
        'l2_result': r.l2_result,
        'inductance_3': r.inductance_3,
        'l3_result': r.l3_result,
        'imported_at': r.imported_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if r.imported_at else '',
    }


def _display_value(value):
    if value is None or value == '':
        return '-'
    if isinstance(value, datetime):
        return value.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, bool):
        return 'PASS' if value else 'FAIL'
    return str(value)


def _model_field_rows(instance, exclude=()):
    rows = []
    excluded = set(exclude)
    for field in instance._meta.fields:
        if field.name in excluded:
            continue
        rows.append((field.verbose_name.title(), _display_value(getattr(instance, field.name))))
    return rows


def _status_color(value):
    text = str(value or '').strip().lower()
    if text in ('pass', 'ok', 'true'):
        return colors.HexColor('#166534')
    if text in ('fail', 'false', 'ng'):
        return colors.HexColor('#991b1b')
    return colors.HexColor('#334155')


def _safe_pdf_filename(value):
    serial = re.sub(r'[^A-Za-z0-9._-]+', '_', value.strip()).strip('._-')
    return serial or 'motor'


class _TraceabilityCanvas:
    def __init__(self, *args, **kwargs):
        from reportlab.pdfgen import canvas
        self._canvas_cls = canvas.Canvas
        self._args = args
        self._kwargs = kwargs
        self._pages = []
        self._canvas = self._canvas_cls(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._canvas, name)

    def showPage(self):
        self._pages.append(dict(self._canvas.__dict__))
        self._canvas._startPage()

    def save(self):
        page_count = len(self._pages) + 1
        self._pages.append(dict(self._canvas.__dict__))
        for state in self._pages:
            self._canvas.__dict__.update(state)
            self._draw_footer(page_count)
            self._canvas.showPage()
        self._canvas.save()

    def _draw_footer(self, page_count):
        self._canvas.saveState()
        self._canvas.setStrokeColor(colors.HexColor('#cbd5e1'))
        self._canvas.line(15 * mm, 14 * mm, 195 * mm, 14 * mm)
        self._canvas.setFont('Helvetica', 7)
        self._canvas.setFillColor(colors.HexColor('#64748b'))
        self._canvas.drawString(15 * mm, 9 * mm, 'Napino Control Systems Pvt. Ltd.')
        self._canvas.drawRightString(195 * mm, 9 * mm, f'Page {self._canvas.getPageNumber()} of {page_count}')
        self._canvas.restoreState()


def _section_heading(text, styles):
    return Paragraph(xml_escape(str(text)), styles['SectionHeading'])


def _details_table(rows, styles, col_widths=None):
    if not rows:
        rows = [('Status', 'Record not available')]

    table_data = []
    for label, value in rows:
        table_data.append([
            Paragraph(xml_escape(str(label)), styles['FieldLabel']),
            Paragraph(xml_escape(_display_value(value)), styles['FieldValue']),
        ])

    table = Table(table_data, colWidths=col_widths or [52 * mm, 118 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return table


def _result_summary_table(link, rotor, stator, styles):
    data = [
        [
            Paragraph('Motor Sr No', styles['SummaryLabel']),
            Paragraph('Rotor Sr No', styles['SummaryLabel']),
            Paragraph('Rotor Result', styles['SummaryLabel']),
            Paragraph('Stator Sr No', styles['SummaryLabel']),
            Paragraph('Stator Result', styles['SummaryLabel']),
        ],
        [
            Paragraph(xml_escape(link.motor_serial), styles['SummaryValue']),
            Paragraph(xml_escape(link.rotor_serial), styles['SummaryValue']),
            Paragraph(xml_escape(rotor.result if rotor else 'Pending'), styles['SummaryValue']),
            Paragraph(xml_escape(link.stator_serial), styles['SummaryValue']),
            Paragraph(xml_escape(stator.final_result if stator else 'Pending'), styles['SummaryValue']),
        ],
    ]
    table = Table(data, colWidths=[35 * mm, 35 * mm, 30 * mm, 35 * mm, 35 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.45, colors.HexColor('#94a3b8')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('TEXTCOLOR', (2, 1), (2, 1), _status_color(rotor.result if rotor else '')),
        ('TEXTCOLOR', (4, 1), (4, 1), _status_color(stator.final_result if stator else '')),
    ]))
    return table


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='CompanyTitle',
        parent=styles['Title'],
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        fontSize=19,
        leading=23,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name='CertificateTitle',
        parent=styles['Heading2'],
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#475569'),
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name='SectionHeading',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=10,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name='FieldLabel',
        parent=styles['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#475569'),
    ))
    styles.add(ParagraphStyle(
        name='FieldValue',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0f172a'),
    ))
    styles.add(ParagraphStyle(
        name='SummaryLabel',
        parent=styles['BodyText'],
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name='SummaryValue',
        parent=styles['BodyText'],
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0f172a'),
    ))
    styles.add(ParagraphStyle(
        name='MetaText',
        parent=styles['BodyText'],
        alignment=TA_RIGHT,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#64748b'),
    ))
    return styles


def _logo_flowable():
    logo_path = finders.find('images/ncs_logo.png') or str(settings.BASE_DIR / 'static' / 'images' / 'ncs_logo.png')
    try:
        return Image(logo_path, width=34 * mm, height=17 * mm, kind='proportional')
    except Exception:
        return Spacer(1, 17 * mm)


def _build_motor_traceability_pdf(link, rotor, stator):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=13 * mm,
        bottomMargin=20 * mm,
        title=f'Motor Traceability {link.motor_serial}',
    )
    styles = _pdf_styles()
    story = [
        _logo_flowable(),
        Paragraph('Napino Control Systems', styles['CompanyTitle']),
        Paragraph('EVR Motor Traceability Certificate', styles['CertificateTitle']),
        _result_summary_table(link, rotor, stator, styles),
    ]

    master_serial = Serial.objects.filter(serial_number__iexact=link.motor_serial).first()
    master_part = Part.objects.filter(serial_number__iexact=link.motor_serial).first()
    motor_rows = _model_field_rows(link, exclude=('id',))
    if master_serial:
        motor_rows.extend(_model_field_rows(master_serial, exclude=('id', 'serial_number')))
    if master_part:
        motor_rows.extend([(f'Part {label}', value) for label, value in _model_field_rows(master_part, exclude=('id', 'serial_number'))])

    story.extend([
        _section_heading('Motor Details', styles),
        _details_table(motor_rows, styles),
        _section_heading('Rotor Details', styles),
        _details_table(_model_field_rows(rotor, exclude=('id',)) if rotor else [('Status', 'Rotor balancing record not yet created')], styles),
        _section_heading('Stator Details', styles),
        _details_table(_model_field_rows(stator, exclude=('id',)) if stator else [('Status', 'Stator testing record not yet created')], styles),
    ])

    doc.build(story, canvasmaker=_TraceabilityCanvas)
    buffer.seek(0)
    return buffer


@page_access_required('motor_traceability')
def motor_traceability_pdf_view(request, motor_sr_no):
    motor_serial = motor_sr_no.strip()
    link = MotorAssembly.objects.filter(motor_serial__iexact=motor_serial).first()
    if not link:
        raise Http404('Motor traceability record not found')
    if not link.rotor_serial or not link.stator_serial:
        raise Http404('Rotor/Stator link missing for this motor')

    rotor = _latest_rotor_balancing(link.rotor_serial)
    stator = StatorTestingRecord.objects.filter(serial_number__iexact=link.stator_serial).first()
    pdf = _build_motor_traceability_pdf(link, rotor, stator)

    filename = f"MotorTraceability_{_safe_pdf_filename(link.motor_serial)}.pdf"
    response = HttpResponse(pdf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@api_access_required('traceability_read')
def api_traceability_search(request):
    serial = clean_scan_data(request.query_params.get('serial', ''))
    if not serial:
        return Response({'detail': 'serial parameter is required'}, status=400)
    
    response_data = {}
    
    # Laser Marking
    laser = Serial.objects.filter(serial_number__iexact=serial).first()
    if laser:
        response_data['laser_marking'] = {
            'id': laser.id,
            'serial_number': laser.serial_number,
            'part_number': laser.part_number,
            'line_no': laser.line_no,
            'shift': laser.shift,
            'part_type': laser.part_type or '',
            'status': laser.status,
            'created_at': laser.created_at.astimezone(IST).isoformat() if laser.created_at else '—',
        }
        
    # Rotor Balancing
    rotor = _latest_rotor_balancing(serial)
    if rotor:
        rotor_payload = _rotor_balancing_payload(rotor)
        rotor_payload['latest_attempt'] = rotor_payload['attempt_no']
        rotor_payload['attempt_count'] = RotorBalancing.objects.filter(serial_number__iexact=serial).count()
        rotor_payload['attempts'] = _rotor_balancing_history_payload(serial)
        response_data['rotor_balancing'] = rotor_payload
        
    # Stator Testing
    stator = StatorTestingRecord.objects.filter(serial_number__iexact=serial).first()
    if stator:
        response_data['stator_testing'] = _stator_testing_payload(stator)
        
    # Magnet Insertion
    magnet = MagnetInsertion.objects.filter(stack_serial__iexact=serial).first()
    if magnet:
        response_data['magnet_insertion'] = {
            'id': magnet.id,
            'stack_serial': magnet.stack_serial,
            'magnet_serial': magnet.magnet_serial,
            'cycle_time': magnet.cycle_time,
            'pass_fail': magnet.pass_fail,
            'result': 'PASS' if magnet.pass_fail else 'FAIL',
            'shift': magnet.shift,
            'operator': magnet.operator.get_full_name() if magnet.operator else '',
            'timestamp': magnet.timestamp.astimezone(IST).isoformat() if magnet.timestamp else '',
        }

    if not response_data:
        return Response({'detail': 'No Record Found'}, status=404)
        
    return Response(response_data)


@api_view(['GET'])
@api_access_required('traceability_read')
def api_scanner_poll(request):
    try:
        from utils.serial_reader import read_scan_line

        cleaned_value = read_scan_line(
            port=settings.SCANNER_PORT,
            baudrate=settings.SCANNER_BAUDRATE,
            timeout=settings.SCANNER_TIMEOUT,
        )
        if cleaned_value:
            return Response({"data": cleaned_value, "received": True})

        return Response({"received": False})
    except Exception:
        logger.exception('Scanner poll failed')
        return Response({"detail": "Scanner unavailable"}, status=503)


# ══════════════════════════════════════════════════════════════════════════════
# PARTS API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@api_access_required('part_lookup')
def api_part_lookup(request):
    part_no = request.query_params.get('part_no', '').strip()
    if not part_no:
        return Response({'detail': 'part_no is required'}, status=400)

    # 1. Primary lookup: Check the Part table (parts manually added via Add Part page)
    part = Part.objects.filter(part_number=part_no).first()
    if part and part.part_name:
        return Response({
            'part_name': part.part_name,
            'part_type': part.part_name,
        })

    # 2. Secondary lookup: Check the Serial table (parts received from laser marking)
    serial = Serial.objects.filter(part_number=part_no).exclude(part_type='').first()
    if serial and serial.part_type:
        return Response({
            'part_name': serial.part_type,
            'part_type': serial.part_type,
        })

    # If neither table has a record with a known name for this part number
    return Response({'detail': 'Part not found'}, status=404)




@api_view(['GET'])
@api_access_required('laser_read')
def api_check_serial(request):
    serial = request.query_params.get('serial', '').strip().upper()
    if not serial:
        return Response({'detail': 'serial is required'}, status=400)
    exists = Serial.objects.filter(serial_number=serial).exists()
    return Response({'exists': exists})


@api_view(['POST'])
@api_access_required('add_part_write')
def api_add_part(request):
    try:
        serial_number = _request_text(request.data, 'serial_number', label='Serial number', max_length=32, upper=True)
        part_number = _request_text(request.data, 'part_number', label='Part number', max_length=5)
        part_name = _request_text(request.data, 'part_name', label='Part name', max_length=50)
        line_no = _request_text(request.data, 'line_no', label='Line number', max_length=2)
        shift_val = _request_text(request.data, 'shift', max_length=1, upper=True)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)

    if not part_number.isdigit() or len(part_number) != 5:
        return Response({'detail': 'Part number must be exactly 5 digits'}, status=400)
    if not part_name:
        return Response({'detail': 'Part name is required'}, status=400)
    if not line_no.isdigit() or len(line_no) != 2:
        return Response({'detail': 'Line number must be 2 digits (e.g. 01)'}, status=400)
    if shift_val not in ('A', 'B', 'C', 'G'):
        return Response({'detail': 'Shift must be A, B, C, or G'}, status=400)

    if Part.objects.filter(serial_number__iexact=serial_number).exists():
        return Response({'detail': 'Serial number already exists.'}, status=400)

    user = request.user
    full_name = (user.get_full_name() or user.username if user.is_authenticated else '')[:100]

    try:
        new_part = Part.objects.create(
            serial_number=serial_number,
            part_number=part_number,
            part_name=part_name,
            line_no=line_no,
            shift=shift_val,
            added_by=full_name,
        )
        return Response({
            'id': new_part.id,
            'part_number': new_part.part_number,
            'part_name': new_part.part_name,
            'line_no': new_part.line_no,
            'shift': new_part.shift,
            'added_by': new_part.added_by,
            'created_at': new_part.created_at.astimezone(IST).isoformat() if new_part.created_at else '—',
        })
    except IntegrityError:
        return Response({'detail': 'Serial number already exists.'}, status=409)
    except DatabaseError:
        logger.exception('Could not add part')
        return Response({'detail': 'Could not add part.'}, status=500)


@api_view(['GET'])
@api_access_required('parts_read')
def api_parts(request):
    parts = Part.objects.all()
    data = []
    for p in parts:
        data.append({
            'id': p.id,
            'serial_number': p.serial_number or '',
            'part_number': p.part_number,
            'part_name': p.part_name,
            'line_no': p.line_no,
            'shift': p.shift,
            'added_by': p.added_by,
            'created_at': p.created_at.astimezone(IST).isoformat() if p.created_at else '—',
        })
    return Response(data)


@api_view(['DELETE'])
@api_access_required('part_delete')
def api_delete_part(request, part_id):
    try:
        Part.objects.get(id=part_id)
    except Part.DoesNotExist:
        return Response({'detail': 'Part not found'}, status=404)
    return Response({
        'detail': 'Production traceability records are immutable and cannot be deleted.'
    }, status=409)


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTION LOG API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@api_access_required('production_log_read')
def api_production_log(request):
    """Return 7-day aggregated production data."""
    part_type = request.query_params.get('part_type', '').strip()
    line_no = request.query_params.get('line_no', '').strip()
    if line_no and (not line_no.isdigit() or len(line_no) != 2):
        return Response({'detail': 'line_no must be exactly 2 digits'}, status=400)
    today = django_tz.localdate()
    start_date = today - timedelta(days=6)

    qs = Serial.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=today,
    )
    if part_type:
        qs = qs.filter(part_type__iexact=part_type)
    if line_no:
        qs = qs.filter(line_no=line_no)
    serials = list(qs)

    # Build daily + shift matrix
    days = [(start_date + timedelta(days=i)).isoformat() for i in range(7)]

    daily_data = {}
    for d in days:
        daily_data[d] = {'date': d, 'A': 0, 'B': 0, 'C': 0, 'G': 0,
                         'total': 0, 'marked': 0, 'pending': 0}

    part_counts = {}
    for s in serials:
        if not s.created_at:
            continue
        d = django_tz.localtime(s.created_at).date().isoformat()
        if d not in daily_data:
            continue
        daily_data[d]['total'] += 1
        shift = s.shift.upper() if s.shift else ''
        if shift in ('A', 'B', 'C', 'G'):
            daily_data[d][shift] += 1
        if s.status == 'Marked':
            daily_data[d]['marked'] += 1
        else:
            daily_data[d]['pending'] += 1
        pn = s.part_number or 'Unknown'
        part_counts[pn] = part_counts.get(pn, 0) + 1

    daily_list = [daily_data[d] for d in days]

    total_parts = sum(row['total'] for row in daily_list)
    total_marked = sum(row['marked'] for row in daily_list)
    daily_avg = round(total_parts / 7, 1) if total_parts else 0
    peak_day = max(daily_list, key=lambda r: r['total'])
    mark_rate = round((total_marked / total_parts) * 100, 1) if total_parts else 0

    shift_totals = {'A': 0, 'B': 0, 'C': 0, 'G': 0}
    for row in daily_list:
        for sh in ('A', 'B', 'C', 'G'):
            shift_totals[sh] += row[sh]

    top_parts = sorted(part_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_parts_list = []
    for pn, cnt in top_parts:
        type_counts = {}
        for s in serials:
            if s.part_number == pn:
                pt = s.part_type or 'N/A'
                type_counts[pt] = type_counts.get(pt, 0) + 1
        most_common_type = 'N/A'
        if type_counts:
            most_common_type = max(type_counts.items(), key=lambda x: x[1])[0]
        top_parts_list.append({
            'part_number': pn,
            'count': cnt,
            'part_type': most_common_type,
            'percentage': round((cnt / total_parts) * 100, 1) if total_parts else 0,
        })

    return Response({
        'kpi': {
            'total_parts': total_parts,
            'daily_avg': daily_avg,
            'peak_day': peak_day['date'],
            'peak_count': peak_day['total'],
            'mark_rate': mark_rate,
        },
        'daily': daily_list,
        'shift_totals': shift_totals,
        'top_parts': top_parts_list,
    })


@api_view(['GET'])
@api_access_required('production_log_read')
def api_production_log_day(request):
    """Return individual serial records for a specific date."""
    day_value = request.query_params.get('day', '').strip()
    part_type = request.query_params.get('part_type', '').strip()
    line_no = request.query_params.get('line_no', '').strip()
    if day_value:
        try:
            day = date.fromisoformat(day_value)
        except (TypeError, ValueError):
            return Response({'detail': 'day must be a valid date in YYYY-MM-DD format'}, status=400)
    else:
        day = django_tz.localdate()
    if line_no and (not line_no.isdigit() or len(line_no) != 2):
        return Response({'detail': 'line_no must be exactly 2 digits'}, status=400)

    qs = Serial.objects.filter(created_at__date=day)
    if part_type:
        qs = qs.filter(part_type__iexact=part_type)
    if line_no:
        qs = qs.filter(line_no=line_no)
    serials = qs.order_by('-created_at')

    records = []
    shift_counts = {'A': 0, 'B': 0, 'C': 0, 'G': 0}
    marked = 0
    for s in serials:
        shift = s.shift.upper() if s.shift else ''
        if shift in shift_counts:
            shift_counts[shift] += 1
        if s.status == 'Marked':
            marked += 1
        records.append({
            'serial_number': s.serial_number,
            'part_number': s.part_number,
            'line_no': s.line_no,
            'shift': s.shift,
            'part_type': s.part_type or '',
            'status': s.status,
            'created_at': s.created_at.astimezone(IST).isoformat() if s.created_at else '—',
            'rotor_result': getattr(_latest_rotor_balancing(s.serial_number), 'result', None)
        })

    return Response({
        'date': day.isoformat(),
        'total': len(records),
        'marked': marked,
        'pending': len(records) - marked,
        'shifts': shift_counts,
        'records': records,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ROTOR BALANCING API
# ══════════════════════════════════════════════════════════════════════════════

def _parse_rotor_recorded_at(date_val, time_val):
    """Parse dd-mm-yy + hh:mm:ss from Excel row values (native datetime or strings)."""
    recorded_at = None
    try:
        parsed_date = None
        parsed_time = None

        if isinstance(date_val, dt.datetime):
            parsed_date = date_val.date()
        elif isinstance(date_val, dt.date):
            parsed_date = date_val
        elif isinstance(date_val, (int, float)):
            parsed_date = openpyxl.utils.datetime.from_excel(date_val).date()
        elif isinstance(date_val, str):
            date_str = date_val.strip()
            for fmt in ("%d-%m-%y", "%d-%m-%Y", "%d/%m/%y", "%d/%m/%Y", "%d.%m.%y", "%d.%m.%Y", "%Y-%m-%d"):
                try:
                    parsed_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    pass

        if isinstance(time_val, dt.datetime):
            parsed_time = time_val.time()
        elif isinstance(time_val, dt.time):
            parsed_time = time_val
        elif isinstance(time_val, dt.timedelta):
            seconds = int(time_val.total_seconds()) % 86400
            parsed_time = (dt.datetime.min + timedelta(seconds=seconds)).time()
        elif isinstance(time_val, (int, float)):
            seconds = int(round((float(time_val) % 1) * 86400))
            parsed_time = (dt.datetime.min + timedelta(seconds=seconds)).time()
        elif isinstance(time_val, str):
            time_str = time_val.strip()
            for fmt in ("%H:%M:%S", "%H:%M:%S.%f", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
                try:
                    parsed_time = datetime.strptime(time_str, fmt).time()
                    break
                except ValueError:
                    pass

        if parsed_date and parsed_time:
            recorded_at = dt.datetime.combine(parsed_date, parsed_time)
        elif isinstance(date_val, dt.datetime):
            recorded_at = date_val

        if recorded_at and django_tz.is_naive(recorded_at):
            recorded_at = django_tz.make_aware(recorded_at)
    except (ValueError, TypeError):
        pass
    return recorded_at


@api_view(['POST'])
@api_access_required('rotor_write')
@transaction.atomic
def api_rotor_balancing_import(request):
    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response({'detail': 'No file uploaded'}, status=400)

    try:
        _validate_import_upload(file_obj)
        suffix = Path(file_obj.name or '').suffix.lower()
        if suffix == '.xls':
            file_obj.seek(0)
            dataframe = pd.read_excel(file_obj, engine='xlrd')
            _validate_import_dimensions(len(dataframe.index) + 1, len(dataframe.columns))
            headers = [str(value).strip() if value is not None else '' for value in dataframe.columns]
            data_rows = dataframe.itertuples(index=False, name=None)
        else:
            file_obj.seek(0)
            workbook = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
            sheet = workbook.active
            _validate_import_dimensions(sheet.max_row, sheet.max_column)
            headers = [
                str(cell.value).strip() if cell.value is not None else ''
                for cell in sheet[1]
            ]
            data_rows = sheet.iter_rows(min_row=2, values_only=True)
            
        try:
            req_cols = ['dd-mm-yy', 'hh:mm:ss', 'Rotor-Type', 'Rotor-Ident', 'Mea-Run', 'Bal-Run', 'RpM', 'PL1[G_MM]', 'PL1[DEG]', 'PL2[G_MM]', 'PL2[DEG]', 'InTol']
            col_indices = {col: headers.index(col) for col in req_cols}
        except ValueError as e:
            return Response({'detail': f'Missing expected column: {e}'}, status=400)

        # Schenck exports record the measurement timestamp as column A date + column B time.
        date_col_index = col_indices.get('dd-mm-yy', 0)
        time_col_index = col_indices.get('hh:mm:ss', 1)

        imported = 0
        updated = 0
        file_attempt_counts = {}
        
        def safe_int(val):
            if val is None or (not isinstance(val, str) and pd.isna(val)):
                return None
            try:
                parsed = float(val)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(parsed):
                raise ValueError('Rotor workbook contains a non-finite integer measurement.')
            return int(parsed)
            
        def safe_float(val):
            if val is None or (not isinstance(val, str) and pd.isna(val)):
                return None
            try:
                parsed = float(val)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(parsed):
                raise ValueError('Rotor workbook contains a non-finite measurement.')
            return parsed

        for row in data_rows:
            if not row: continue
            sn_val = row[col_indices['Rotor-Ident']]
            if not sn_val: continue
                
            serial_num = str(sn_val).strip()
            if len(serial_num) > 32:
                raise ValueError('Rotor serial numbers must be no more than 32 characters.')
            serial_key = serial_num.lower()
            file_attempt_counts[serial_key] = file_attempt_counts.get(serial_key, 0) + 1
            incoming_attempt_no = file_attempt_counts[serial_key]
            result_val = str(row[col_indices['InTol']]).strip().upper()
            rotor_type_val = str(row[col_indices['Rotor-Type']] or '').strip()
            if len(rotor_type_val) > 100:
                raise ValueError('Rotor type must be no more than 100 characters.')
            
            date_val = row[date_col_index]
            time_val = row[time_col_index]
            recorded_at = _parse_rotor_recorded_at(date_val, time_val)

            final_res = 'Pass' if result_val == 'Y' else 'Fail'

            with transaction.atomic():
                row_data = {
                    'result': final_res,
                    'rotor_type': rotor_type_val,
                    'recorded_at': recorded_at,
                    'measure_run': safe_int(row[col_indices['Mea-Run']]),
                    'balancing_run': safe_int(row[col_indices['Bal-Run']]),
                    'rpm': safe_int(row[col_indices['RpM']]),
                    'plane1_weight': safe_float(row[col_indices['PL1[G_MM]']]),
                    'plane1_degree': safe_float(row[col_indices['PL1[DEG]']]),
                    'plane2_weight': safe_float(row[col_indices['PL2[G_MM]']]),
                    'plane2_degree': safe_float(row[col_indices['PL2[DEG]']]),
                }
                existing_attempt = RotorBalancing.objects.filter(
                    serial_number__iexact=serial_num,
                    attempt_no=incoming_attempt_no,
                ).first()
                if existing_attempt and existing_attempt.recorded_at is None:
                    for field, value in row_data.items():
                        setattr(existing_attempt, field, value)
                    existing_attempt.save(update_fields=list(row_data.keys()))
                    updated += 1
                elif existing_attempt and recorded_at and existing_attempt.recorded_at == recorded_at:
                    continue
                else:
                    attempt_no = RotorBalancing.objects.filter(serial_number__iexact=serial_num).count() + 1
                    RotorBalancing.objects.create(
                        serial_number=serial_num,
                        attempt_no=attempt_no,
                        **row_data,
                    )
                    imported += 1
                
        return Response({'detail': f'{imported} rotor balancing attempts imported, {updated} existing attempts updated.'})

    except ValueError as exc:
        transaction.set_rollback(True)
        return Response({'detail': str(exc)}, status=400)
    except Exception:
        transaction.set_rollback(True)
        logger.exception('Error importing rotor balancing records')
        return Response({'detail': 'Could not parse the uploaded workbook.'}, status=400)


@api_view(['GET'])
@api_access_required('rotor_read')
def api_rotor_balancing_list(request):
    records = RotorBalancing.objects.all().order_by('-imported_at')[:200]
    return Response([_rotor_balancing_payload(r) for r in records])


@api_view(['GET'])
@api_access_required('rotor_read')
def api_rotor_balancing_by_serial(request, serial):
    serial = serial.strip()
    if not serial:
        return Response({'detail': 'Rotor serial is required', 'code': 'serial_required'}, status=400)

    record = _latest_rotor_balancing(serial)
    if not record:
        return Response({
            'detail': 'Rotor balancing record not yet created',
            'code': 'rotor_balancing_not_created',
        }, status=404)

    payload = _rotor_balancing_payload(record)
    payload['latest_attempt'] = payload['attempt_no']
    payload['attempt_count'] = RotorBalancing.objects.filter(serial_number__iexact=serial).count()
    payload['attempts'] = _rotor_balancing_history_payload(serial)
    return Response(payload)

@api_view(['DELETE'])
@api_access_required('rotor_write')
def api_rotor_balancing_delete(request, pk):
    try:
        RotorBalancing.objects.get(pk=pk)
    except RotorBalancing.DoesNotExist:
        return Response({'success': False, 'error': 'Record not found'}, status=404)
    return Response({
        'success': False,
        'detail': 'Production traceability records are immutable and cannot be deleted.',
    }, status=409)


# ══════════════════════════════════════════════════════════════════════════════
# STATOR TESTING API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['POST'])
@api_access_required('stator_write')
@transaction.atomic
def api_stator_testing_import(request):
    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response({'detail': 'No file uploaded'}, status=400)

    try:
        _validate_import_upload(file_obj)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)

    suffix = Path(file_obj.name or '').suffix.lower()
    try:
        file_obj.seek(0)
        if suffix == '.csv':
            df = pd.read_csv(file_obj)
        elif suffix == '.tsv':
            df = pd.read_csv(file_obj, sep='\t')
        elif suffix == '.xls':
            try:
                df = pd.read_excel(file_obj, engine='xlrd')
            except Exception:
                # Some machine exports use a .xls name for tab-separated text.
                file_obj.seek(0)
                df = pd.read_csv(file_obj, sep='\t')
        else:
            df = pd.read_excel(file_obj, engine='openpyxl')
    except Exception:
        logger.exception('Could not parse stator testing upload')
        return Response(
            {'detail': 'Could not parse file. Please upload a valid TSV, CSV, XLS, or XLSX file.'},
            status=400,
        )

    try:
        _validate_import_dimensions(len(df.index), len(df.columns))
        # 2. Normalize Column Names (strip whitespace and uppercase for matching)
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Mapping of expected columns to data frame columns
        col_map = {}
        
        # Fuzzy matching for required columns
        required_logic = {
            'BAR CODE': ['BAR CODE', 'BARCODE', 'SERIAL NUMBER', 'SERIAL', 'SN', 'BAR_CODE'],
            'DATE': ['DATE', 'DATETIME', 'TIME', 'TIMESTAMP', 'RECORDED_AT', 'RECORDED AT'],
            'FINAL RESULT': ['FINAL RESULT', 'FINAL_RESULT', 'RESULT', 'STATUS', 'RESLUT']
        }
        
        for key, alternates in required_logic.items():
            for alt in alternates:
                if alt in df.columns:
                    col_map[key] = alt
                    break
        
        missing = [k for k in required_logic.keys() if k not in col_map]
        if missing:
            return Response({
                'detail': f'Missing required columns: {", ".join(missing)}.',
                'found': list(df.columns[:10]),
                'help': 'Please ensure your file has headers like "BAR CODE", "DATE", and "FINAL RESULT".'
            }, status=400)

        # Optional columns mapping
        optional_logic = {
            'OPERATOR': ['OPERATOR', 'USER', 'NAME'],
            'CODE NUMBER': ['CODE NUMBER', 'PART NUMBER', 'PART NO', 'CODE'],
            '%SYMMETRY': ['%SYMMETRY', 'SYMMETRY', 'SYM'],
            'R/Y': ['R/Y', 'RY', 'R-Y'],
            'R/Y RESULT': ['R/Y RESULT', 'RY RESULT', 'RY_RESULT'],
            'Y/B': ['Y/B', 'YB', 'Y-B'],
            'Y/B RESULT': ['Y/B RESULT', 'YB RESULT', 'YB_RESULT'],
            'B/R': ['B/R', 'BR', 'B-R'],
            'B/R RESULT': ['B/R RESULT', 'BR RESULT', 'BR_RESULT'],
            'THD WIN': ['THD WIN', 'THD'],
            'THD RESULT': ['THD RESULT', 'THD_RESULT'],
            'IR (M OHMS)': ['IR (M OHMS)', 'IR', 'INSULATION RESISTANCE'],
            'IR RESULT': ['IR RESULT', 'IR_RESULT'],
            'HIGH VOLTAGE': ['HIGH VOLTAGE', 'HV', 'HIPOT'],
            'HIGH VOLTAGE RESULT': ['HIGH VOLTAGE RESULT', 'HV RESULT', 'HV_RESULT', 'HIPOT RESULT'],
            'SURGE VOLTAGE': ['SURGE VOLTAGE', 'SURGE'],
            'SURGE MAIN (R/Y) - ERROR%': [
                'SURGE MAIN (R/Y) - ERROR%',
                'SURGE MAIN R/Y ERROR%',
                'SURGE RY ERROR',
            ],
            'SURGE R/Y RESULT': ['SURGE R/Y RESULT', 'SURGE RY RESULT', 'SURGE_RY_RESULT'],
            'SURGE AUX (Y/B) - ERROR%': [
                'SURGE AUX (Y/B) - ERROR%',
                'SURGE AUX Y/B ERROR%',
                'SURGE YB ERROR',
            ],
            'SURGE AUX (Y/B) RESULT': ['SURGE AUX (Y/B) RESULT', 'SURGE YB RESULT', 'SURGE_YB_RESULT'],
            'SURGE MAIN-AUX (B/R) - ERROR%': [
                'SURGE MAIN-AUX (B/R) - ERROR%',
                'SURGE MAIN-AUX B/R ERROR%',
                'SURGE BR ERROR',
            ],
            'SURGE MAIN-AUX (B/R) RESULT': ['SURGE MAIN-AUX (B/R) RESULT', 'SURGE BR RESULT', 'SURGE_BR_RESULT'],
            'INDUCTANCE-1': ['INDUCTANCE-1', 'L1', 'IND-1'],
            'INDUCTANCE-1 RESULT': ['INDUCTANCE-1 RESULT', 'L1 RESULT', 'L1_RESULT'],
            'INDUCTANCE-2': ['INDUCTANCE-2', 'L2', 'IND-2'],
            'INDUCTANCE-2 RESULT': ['INDUCTANCE-2 RESULT', 'L2 RESULT', 'L2_RESULT'],
            'INDUCTANCE-3': ['INDUCTANCE-3', 'L3', 'IND-3'],
            'INDUCTANCE-3 RESULT': ['INDUCTANCE-3 RESULT', 'L3 RESULT', 'L3_RESULT'],
        }
        
        for key, alternates in optional_logic.items():
            for alt in alternates:
                if alt in df.columns:
                    col_map[key] = alt
                    break

        imported = 0
        skipped = 0

        def get_val(row, key):
            col_name = col_map.get(key)
            if col_name and col_name in row:
                val = row[col_name]
                if pd.isna(val): return None
                return str(val).strip()
            return None

        for index, row in df.iterrows():
            sn_val = (get_val(row, 'BAR CODE') or '').upper()
            if not sn_val or sn_val.lower() == 'nan': 
                continue
            if len(sn_val) > 32:
                raise ValueError('Stator serial numbers must be no more than 32 characters.')
                
            if StatorTestingRecord.objects.filter(serial_number__iexact=sn_val).exists():
                skipped += 1
                continue

            date_val = get_val(row, 'DATE')
            recorded_at = None
            if date_val:
                try:
                    row_dt = pd.to_datetime(date_val, dayfirst=True, errors='coerce')
                    if pd.notna(row_dt):
                        plant_timezone = django_tz.get_current_timezone()
                        if row_dt.tzinfo is None:
                            recorded_at = django_tz.make_aware(
                                row_dt.to_pydatetime(),
                                plant_timezone,
                            )
                        else:
                            recorded_at = row_dt.to_pydatetime().astimezone(plant_timezone)
                except Exception:
                    pass

            res_val = get_val(row, 'FINAL RESULT') or 'N/A'
            if len(res_val) > 20: res_val = res_val[:20]

            record_data = {
                'serial_number': sn_val,
                'recorded_at': recorded_at,
                'final_result': res_val,
                'operator': get_val(row, 'OPERATOR'),
                'code_number': get_val(row, 'CODE NUMBER'),
                'symmetry': get_val(row, '%SYMMETRY'),
                'ry': get_val(row, 'R/Y'),
                'ry_result': get_val(row, 'R/Y RESULT'),
                'yb': get_val(row, 'Y/B'),
                'yb_result': get_val(row, 'Y/B RESULT'),
                'br': get_val(row, 'B/R'),
                'br_result': get_val(row, 'B/R RESULT'),
                'thd_win': get_val(row, 'THD WIN'),
                'thd_result': get_val(row, 'THD RESULT'),
                'ir_m_ohms': get_val(row, 'IR (M OHMS)'),
                'ir_result': get_val(row, 'IR RESULT'),
                'high_voltage': get_val(row, 'HIGH VOLTAGE'),
                'hv_result': get_val(row, 'HIGH VOLTAGE RESULT'),
                'surge_voltage': get_val(row, 'SURGE VOLTAGE'),
                'surge_main_ry_error': get_val(row, 'SURGE MAIN (R/Y) - ERROR%'),
                'surge_ry_result': get_val(row, 'SURGE R/Y RESULT'),
                'surge_aux_yb_error': get_val(row, 'SURGE AUX (Y/B) - ERROR%'),
                'surge_aux_yb_result': get_val(row, 'SURGE AUX (Y/B) RESULT'),
                'surge_main_aux_br_error': get_val(row, 'SURGE MAIN-AUX (B/R) - ERROR%'),
                'surge_main_aux_br_result': get_val(row, 'SURGE MAIN-AUX (B/R) RESULT'),
                'inductance_1': get_val(row, 'INDUCTANCE-1'),
                'l1_result': get_val(row, 'INDUCTANCE-1 RESULT'),
                'inductance_2': get_val(row, 'INDUCTANCE-2'),
                'l2_result': get_val(row, 'INDUCTANCE-2 RESULT'),
                'inductance_3': get_val(row, 'INDUCTANCE-3'),
                'l3_result': get_val(row, 'INDUCTANCE-3 RESULT'),
            }
            for field_name, value in record_data.items():
                model_field = StatorTestingRecord._meta.get_field(field_name)
                if (
                    value is not None
                    and model_field.max_length is not None
                    and len(str(value)) > model_field.max_length
                ):
                    raise ValueError(
                        f'{model_field.verbose_name.title()} exceeds '
                        f'{model_field.max_length} characters.'
                    )
            StatorTestingRecord.objects.create(**record_data)
            imported += 1

        return Response({'detail': f'{imported} records imported, {skipped} skipped (already existed).'})

    except ValueError as exc:
        transaction.set_rollback(True)
        return Response({'detail': str(exc)}, status=400)
    except Exception:
        transaction.set_rollback(True)
        logger.exception('Error importing stator testing records')
        return Response({'detail': 'Could not import the uploaded file.'}, status=400)


@api_view(['GET'])
@api_access_required('stator_read')
def api_stator_testing_list(request):
    records = StatorTestingRecord.objects.all().order_by('-imported_at')[:200]
    return Response([_stator_testing_payload(r) for r in records])


@api_view(['GET'])
@api_access_required('stator_read')
def api_stator_testing_by_serial(request, serial):
    serial = serial.strip()
    if not serial:
        return Response({'detail': 'Stator serial is required', 'code': 'serial_required'}, status=400)

    record = StatorTestingRecord.objects.filter(serial_number__iexact=serial).first()
    if not record:
        return Response({
            'detail': 'Stator testing record not yet created',
            'code': 'stator_testing_not_created',
        }, status=404)

    return Response(_stator_testing_payload(record))

@api_view(['DELETE'])
@api_access_required('stator_write')
def api_stator_testing_delete(request, pk):
    try:
        StatorTestingRecord.objects.get(pk=pk)
    except StatorTestingRecord.DoesNotExist:
        return Response({'success': False, 'error': 'Record not found'}, status=404)
    return Response({
        'success': False,
        'detail': 'Production traceability records are immutable and cannot be deleted.',
    }, status=409)


# ══════════════════════════════════════════════════════════════════════════════
# MAGNET INSERTION API
# ══════════════════════════════════════════════════════════════════════════════

# =============================================================================
# MOTOR ASSEMBLY API
# =============================================================================

def _master_serial_for_part(serial_number, part_type):
    serial = Serial.objects.filter(
        serial_number__iexact=serial_number,
        part_type__iexact=part_type,
    ).first()
    if serial:
        return serial.serial_number

    part = Part.objects.filter(
        serial_number__iexact=serial_number,
        part_name__iexact=part_type,
    ).first()
    if part:
        return part.serial_number

    return None


@api_view(['GET'])
@api_access_required('traceability_read')
def api_motor_traceability(request, serial):
    motor_serial = serial.strip()
    if not motor_serial:
        return Response({'detail': 'Motor serial is required', 'code': 'serial_required'}, status=400)

    link = MotorAssembly.objects.filter(motor_serial__iexact=motor_serial).first()
    if not link:
        canonical_motor = _master_serial_for_part(motor_serial, 'Motor')
        if not canonical_motor:
            return Response({
                'detail': 'Motor not found',
                'code': 'motor_not_found',
            }, status=404)
        return Response({
            'detail': 'Rotor/Stator link missing for this motor',
            'code': 'rotor_stator_link_missing',
            'motor_serial': canonical_motor,
        }, status=404)

    if not link.rotor_serial or not link.stator_serial:
        return Response({
            'detail': 'Rotor/Stator link missing for this motor',
            'code': 'rotor_stator_link_missing',
            'motor_serial': link.motor_serial,
            'rotor_serial': link.rotor_serial,
            'stator_serial': link.stator_serial,
        }, status=404)

    rotor = _latest_rotor_balancing(link.rotor_serial)
    stator = StatorTestingRecord.objects.filter(serial_number__iexact=link.stator_serial).first()

    return Response({
        'motor_serial': link.motor_serial,
        'rotor_serial': link.rotor_serial,
        'stator_serial': link.stator_serial,
        'rotor_balancing_created': bool(rotor),
        'stator_testing_created': bool(stator),
        'rotor_result': rotor.result if rotor else '',
        'stator_result': stator.final_result if stator else '',
        'linked_at': link.created_at.astimezone(IST).isoformat() if link.created_at else '',
        'updated_at': link.updated_at.astimezone(IST).isoformat() if link.updated_at else '',
    })


def _motor_assembly_payload(record):
    rotor = _latest_rotor_balancing(record.rotor_serial)
    stator = StatorTestingRecord.objects.filter(serial_number__iexact=record.stator_serial).first()
    return {
        'id': record.id,
        'motor_serial': record.motor_serial,
        'rotor_serial': record.rotor_serial,
        'stator_serial': record.stator_serial,
        'rotor_result': rotor.result if rotor else '',
        'stator_result': stator.final_result if stator else '',
        'created_at': record.created_at.astimezone(IST).isoformat() if record.created_at else '',
        'updated_at': record.updated_at.astimezone(IST).isoformat() if record.updated_at else '',
    }


@api_view(['GET', 'POST'])
def api_motor_assembly(request):
    permission_action = 'motor_assembly_read' if request.method == 'GET' else 'motor_assembly_write'
    if not can_access_action(request.user, permission_action):
        return Response({'detail': 'You do not have permission to perform this action.'}, status=403)

    if request.method == 'GET':
        search = request.query_params.get('search', '').strip()
        records = MotorAssembly.objects.all()
        if search:
            records = records.filter(
                models.Q(motor_serial__icontains=search)
                | models.Q(rotor_serial__icontains=search)
                | models.Q(stator_serial__icontains=search)
            )
        return Response([_motor_assembly_payload(r) for r in records[:200]])

    try:
        motor_serial = _request_text(request.data, 'motor_serial', label='Motor Sr No', max_length=32, upper=True)
        rotor_serial = _request_text(request.data, 'rotor_serial', label='Rotor Sr No', max_length=32, upper=True)
        stator_serial = _request_text(request.data, 'stator_serial', label='Stator Sr No', max_length=32, upper=True)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)

    if not motor_serial:
        return Response({'detail': 'Motor Sr No is required'}, status=400)
    if not rotor_serial:
        return Response({'detail': 'Rotor Sr No is required'}, status=400)
    if not stator_serial:
        return Response({'detail': 'Stator Sr No is required'}, status=400)

    rotor = _latest_rotor_balancing(rotor_serial)
    stator = StatorTestingRecord.objects.filter(serial_number__iexact=stator_serial).first()

    missing = []
    if not rotor:
        missing.append('Rotor Sr No not found in rotor balancing records')
    if not stator:
        missing.append('Stator Sr No not found in stator testing records')
    if missing:
        return Response({'detail': 'Validation failed', 'errors': missing}, status=400)

    failed = []
    if str(rotor.result).strip().lower() != 'pass':
        failed.append('Latest rotor balancing result must be PASS')
    if str(stator.final_result).strip().lower() != 'pass':
        failed.append('Stator testing final result must be PASS')
    if failed:
        return Response({'detail': 'Validation failed', 'errors': failed}, status=400)

    rotor_serial = rotor.serial_number
    stator_serial = stator.serial_number

    rotor_conflict = MotorAssembly.objects.filter(
        rotor_serial__iexact=rotor_serial
    ).exclude(motor_serial__iexact=motor_serial).first()
    if rotor_conflict:
        return Response({
            'detail': 'Rotor Sr No is already linked to a different motor',
            'conflict': _motor_assembly_payload(rotor_conflict),
        }, status=409)

    stator_conflict = MotorAssembly.objects.filter(
        stator_serial__iexact=stator_serial
    ).exclude(motor_serial__iexact=motor_serial).first()
    if stator_conflict:
        return Response({
            'detail': 'Stator Sr No is already linked to a different motor',
            'conflict': _motor_assembly_payload(stator_conflict),
        }, status=409)

    existing = MotorAssembly.objects.filter(motor_serial__iexact=motor_serial).first()
    if existing:
        same_rotor = existing.rotor_serial.lower() == rotor_serial.lower()
        same_stator = existing.stator_serial.lower() == stator_serial.lower()
        if not same_rotor or not same_stator:
            return Response({
                'detail': 'Motor Sr No is already linked to a different rotor/stator. Re-linking is blocked.',
                'conflict': _motor_assembly_payload(existing),
            }, status=409)
        existing.motor_serial = motor_serial
        existing.rotor_serial = rotor_serial
        existing.stator_serial = stator_serial
        existing.save()
        return Response({**_motor_assembly_payload(existing), 'updated': True})

    try:
        with transaction.atomic():
            record = MotorAssembly.objects.create(
                motor_serial=motor_serial,
                rotor_serial=rotor_serial,
                stator_serial=stator_serial,
            )
    except IntegrityError:
        return Response({
            'detail': 'A conflicting motor assembly link already exists. Refresh and try again.'
        }, status=409)

    return Response(_motor_assembly_payload(record), status=201)


@api_view(['GET'])
@api_access_required('magnet_read')
def api_magnet_insertion_list(request):
    records = MagnetInsertion.objects.all().order_by('-timestamp')[:200]
    data = []
    for r in records:
        data.append({
            'id': r.id,
            'stack_serial': r.stack_serial,
            'magnet_serial': r.magnet_serial,
            'cycle_time': r.cycle_time,
            'pass_fail': r.pass_fail,
            'result': 'PASS' if r.pass_fail else 'FAIL',
            'shift': r.shift,
            'operator': r.operator.get_full_name() if r.operator else '',
            'timestamp': r.timestamp.astimezone(IST).isoformat() if r.timestamp else '',
        })
    return Response(data)


@api_view(['POST'])
@api_access_required('magnet_write')
def api_magnet_insertion_create(request):
    try:
        stack_serial = _request_text(request.data, 'stack_serial', label='Stack serial', max_length=64, upper=True)
        magnet_serial = _request_text(request.data, 'magnet_serial', label='Magnet serial', max_length=64, upper=True)
        shift = _request_text(request.data, 'shift', max_length=1, upper=True)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    cycle_time = request.data.get('cycle_time')
    pass_fail = request.data.get('pass_fail')

    if not stack_serial:
        return Response({'detail': 'Stack serial is required'}, status=400)
    if not magnet_serial:
        return Response({'detail': 'Magnet serial is required'}, status=400)
    if cycle_time is None:
        return Response({'detail': 'Cycle time is required'}, status=400)
    if not isinstance(pass_fail, bool):
        return Response({'detail': 'pass_fail must be a JSON boolean'}, status=400)
    if shift not in ('A', 'B', 'C', 'G'):
        return Response({'detail': 'Shift must be A, B, C, or G'}, status=400)

    try:
        cycle_time = float(cycle_time)
    except (ValueError, TypeError):
        return Response({'detail': 'Cycle time must be a number'}, status=400)
    if not math.isfinite(cycle_time) or not 0 < cycle_time <= 3600:
        return Response(
            {'detail': 'Cycle time must be greater than 0 and no more than 3600 seconds'},
            status=400,
        )

    existing = MagnetInsertion.objects.filter(
        stack_serial__iexact=stack_serial,
        magnet_serial__iexact=magnet_serial,
    ).first()
    if existing:
        return Response({
            'id': existing.id,
            'stack_serial': existing.stack_serial,
            'magnet_serial': existing.magnet_serial,
            'cycle_time': existing.cycle_time,
            'pass_fail': existing.pass_fail,
            'result': 'PASS' if existing.pass_fail else 'FAIL',
            'shift': existing.shift,
            'operator': existing.operator.get_full_name() if existing.operator else '',
            'timestamp': existing.timestamp.astimezone(IST).isoformat() if existing.timestamp else '',
            'duplicate': True,
        })

    # Auto-assign operator from logged-in user
    operator = request.user if request.user.is_authenticated else None

    try:
        record = MagnetInsertion.objects.create(
            stack_serial=stack_serial,
            magnet_serial=magnet_serial,
            cycle_time=cycle_time,
            pass_fail=pass_fail,
            shift=shift,
            operator=operator,
        )
        return Response({
            'id': record.id,
            'stack_serial': record.stack_serial,
            'magnet_serial': record.magnet_serial,
            'cycle_time': record.cycle_time,
            'pass_fail': record.pass_fail,
            'result': 'PASS' if record.pass_fail else 'FAIL',
            'shift': record.shift,
            'operator': record.operator.get_full_name() if record.operator else '',
            'timestamp': record.timestamp.astimezone(IST).isoformat() if record.timestamp else '',
        }, status=201)
    except IntegrityError:
        return Response(
            {'detail': 'This stack and magnet serial pair already exists.'},
            status=409,
        )
    except DatabaseError:
        logger.exception('Could not create magnet insertion record')
        return Response({'detail': 'Could not save magnet insertion record.'}, status=500)


@api_view(['GET'])
@api_access_required('magnet_read')
def api_magnet_insertion_stats(request):
    qs = MagnetInsertion.objects.all()
    total = qs.count()
    passed = qs.filter(pass_fail=True).count()
    failed = qs.filter(pass_fail=False).count()
    yield_pct = round((passed / total) * 100, 1) if total > 0 else 0.0

    return Response({
        'total': total,
        'passed': passed,
        'failed': failed,
        'yield_pct': yield_pct,
    })


@api_view(['DELETE'])
@api_access_required('magnet_write')
def api_magnet_insertion_delete(request, pk):
    try:
        MagnetInsertion.objects.get(pk=pk)
    except MagnetInsertion.DoesNotExist:
        return Response({'success': False, 'error': 'Record not found'}, status=404)
    return Response({
        'success': False,
        'detail': 'Production traceability records are immutable and cannot be deleted.',
    }, status=409)


def _decode_modbus_string(registers):
    if not registers: return ""
    b = b''
    for reg in registers:
        b += struct.pack('>H', reg)
    # Strip null bytes and whitespace
    return b.decode('ascii', errors='ignore').strip('\x00').strip()

@api_view(['GET'])
@api_access_required('magnet_read')
def api_magnet_insertion_status(request):
    client = None
    try:
        if not settings.PLC_HOST:
            raise RuntimeError('PLC_HOST is not configured')
        client = ModbusTcpClient(
            settings.PLC_HOST,
            port=settings.PLC_PORT,
            timeout=settings.PLC_TIMEOUT,
        )
        if not client.connect():
            return Response({'connected': False})

        res_mag = client.read_holding_registers(address=3230, count=15, device_id=1)
        magnet_serial = ""
        if not res_mag.isError():
            magnet_serial = _decode_modbus_string(res_mag.registers)

        res_stack = client.read_holding_registers(address=3260, count=15, device_id=1)
        stack_serial = ""
        if not res_stack.isError():
            stack_serial = _decode_modbus_string(res_stack.registers)

        cycle_complete = bool(magnet_serial and stack_serial)

        return Response({
            'connected': True,
            'magnet_serial': magnet_serial or None,
            'stack_serial': stack_serial or None,
            'cycle_complete': cycle_complete,
            # Not yet read from PLC registers — omit so auto-save does not record fake PASS/0s.
            'pass_fail': None,
            'cycle_time': None,
        })
    except Exception:
        logger.exception('PLC status poll failed')
        return Response({
            'connected': False,
            'error': 'PLC unavailable',
        }, status=503)
    finally:
        if client is not None:
            client.close()
