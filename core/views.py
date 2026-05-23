# core/views.py
# Napino MES — All page views + DRF API views
from datetime import date, datetime, timedelta, timezone
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
import openpyxl
import pandas as pd
import datetime as dt
from django.utils import timezone as django_tz
from .models import Serial, Part, RotorBalancing, StatorBalancingRecord

IST = timezone(timedelta(hours=5, minutes=30))

# ── Shared file path ─────────────────────────────────────────────────────────
LASER_SERIAL_FILE = r"\\172.16.61.202\Common Folder\Machine Data\LaserData\serial.txt"


def write_to_shared_file(serial: str) -> None:
    try:
        with open(LASER_SERIAL_FILE, "w", encoding="utf-8", newline="") as f:
            f.write(serial)
    except Exception:
        pass  # On localhost dev, shared drive won't exist


# ── Serial generation helper ─────────────────────────────────────────────────
def generate_serial(part_number: str, line_no: str, shift: str) -> str:
    """
    Format: PPPPP + LL + S + YYDDD + NNN  (3-digit sequence)
    """
    today = date.today()
    yy = today.strftime("%y")
    ddd = today.strftime("%j")
    date_str = f"{yy}{ddd}"

    today_count = Serial.objects.filter(created_at__date=today).count()
    seq = today_count + 1
    if seq > 999:
        raise ValueError("Daily sequence limit of 999 reached for today")

    return f"{part_number}{line_no}{shift}{date_str}{seq:03d}"


# ══════════════════════════════════════════════════════════════════════════════
# ── Page View Helpers ─────────────────────────────────────────────────────────

def _render_page(request, template_name, active_page):
    user = _user_ctx(request.user)
    return render(request, f'core/{template_name}', {'user': user, 'active_page': active_page})

# ── Page Views ────────────────────────────────────────────────────────────────

def root_view(request):
    if request.user.is_authenticated:
        return redirect('/dashboard')
    return render(request, 'core/login.html', {'error': None})


@login_required
def dashboard_view(request):
    return _render_page(request, 'dashboard.html', 'dashboard')


@login_required
def laser_marking_view(request):
    return _render_page(request, 'laser_marking.html', 'laser')


@login_required
def add_part_view(request):
    return _render_page(request, 'add_part.html', 'add_part')


@login_required
def traceability_view(request):
    return _render_page(request, 'traceability.html', 'trace')


@login_required
def machine_overview_view(request):
    return _render_page(request, 'machine_overview.html', 'machine_overview')


@login_required
def shift_report_view(request):
    return _render_page(request, 'shift_report.html', 'shift')


@login_required
def production_log_view(request):
    return _render_page(request, 'production_log.html', 'production_log')


@login_required
def rotor_balancing_view(request):
    return _render_page(request, 'rotor_balancing.html', 'rotor_balancing')


@login_required
def stator_balancing_view(request):
    return _render_page(request, 'stator_balancing.html', 'stator_balancing')


def _user_ctx(user):
    """Build a user context dict matching the old FastAPI session dict."""
    return {
        'username': user.username,
        'full_name': user.get_full_name() or user.username,
        'role': getattr(user, 'profile_role', 'operator') if hasattr(user, 'profile_role') else (user.first_name and 'Graduate Engineering Trainee' or 'operator'),
    }


# ══════════════════════════════════════════════════════════════════════════════
# AUTH API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    username = request.data.get('username', '')
    password = request.data.get('password', '')

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({'detail': 'Invalid username or password'}, status=status.HTTP_401_UNAUTHORIZED)

    login(request, user)
    full_name = user.get_full_name() or user.username
    return Response({'status': 'ok', 'full_name': full_name})


@api_view(['POST'])
@permission_classes([AllowAny])
def api_logout(request):
    logout(request)
    return Response({'status': 'logged out'})


# ══════════════════════════════════════════════════════════════════════════════
# SERIAL API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['POST'])
def api_generate(request):
    part_number = request.data.get('part_number', '')
    line_no = request.data.get('line_no', '')
    shift_val = request.data.get('shift', '')
    part_type = request.data.get('part_type', '')

    if not part_number.isdigit() or len(part_number) != 5:
        return Response({'detail': 'Part number must be exactly 5 digits'}, status=400)
    if not line_no.isdigit() or len(line_no) != 2:
        return Response({'detail': 'Line number must be 2 digits (e.g. 01)'}, status=400)
    if shift_val.upper() not in ('A', 'B', 'C', 'G'):
        return Response({'detail': 'Shift must be A, B, C, or G'}, status=400)

    try:
        serial = generate_serial(part_number, line_no, shift_val.upper())
    except ValueError as e:
        return Response({'detail': str(e)}, status=400)

    # Write to shared laser file
    write_to_shared_file(serial)

    try:
        Serial.objects.create(
            serial_number=serial,
            part_number=part_number,
            line_no=line_no,
            shift=shift_val.upper(),
            part_type=part_type or '',
        )
    except Exception as e:
        return Response({'detail': f'Database error: {e}'}, status=500)

    return Response({'serial': serial, 'status': 'success'})


@api_view(['GET'])
def api_serials(request):
    serials = Serial.objects.all().order_by('-created_at')[:100]
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
            'rotor_result': getattr(RotorBalancing.objects.filter(serial_number__iexact=s.serial_number.strip()).first(), 'result', None)
        })
        
    # Append isolated Rotor Balancing records
    isolated_rotors = RotorBalancing.objects.exclude(serial_number__in=serial_numbers_seen).order_by('-imported_at')[:50]
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
            'rotor_result': r.result
        })
        
    return Response(data)


@api_view(['DELETE'])
def api_delete_serial(request, serial_id):
    try:
        serial = Serial.objects.get(id=serial_id)
    except Serial.DoesNotExist:
        return Response({'detail': 'Serial not found'}, status=404)
    serial.delete()
    return Response({'status': 'deleted'})


@api_view(['POST'])
def api_mark_done(request):
    serial = request.data.get('serial', '')
    try:
        entry = Serial.objects.get(serial_number=serial)
    except Serial.DoesNotExist:
        return Response({'detail': 'Serial not found'}, status=404)

    entry.status = 'Marked'
    entry.save()
    return Response({'serial': serial, 'status': 'Marked'})


@api_view(['GET'])
def api_stats(request):
    today = date.today()
    total_today = Serial.objects.filter(created_at__date=today).count()
    marked_today = Serial.objects.filter(created_at__date=today, status='Marked').count()
    pending_today = Serial.objects.filter(created_at__date=today, status='Pending').count()
    total_all = Serial.objects.count()
    
    rotor_today_objs = RotorBalancing.objects.filter(imported_at__date=today)
    rotor_total = rotor_today_objs.count()
    rotor_pass = rotor_today_objs.filter(result='Pass').count()
    rotor_fail = rotor_today_objs.filter(result='Fail').count()
    
    stator_today_objs = StatorBalancingRecord.objects.filter(imported_at__date=today)
    stator_total = stator_today_objs.count()
    stator_pass = stator_today_objs.filter(final_result__iexact='Pass').count()
    stator_fail = stator_today_objs.filter(final_result__iexact='Fail').count()
    
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
    })


@api_view(['GET'])
def api_traceability_search(request):
    serial = request.query_params.get('serial', '').strip()
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
    rotor = RotorBalancing.objects.filter(serial_number__iexact=serial).first()
    if rotor:
        response_data['rotor_balancing'] = {
            'id': rotor.id,
            'serial_number': rotor.serial_number,
            'result': rotor.result,
            'rotor_type': rotor.rotor_type or '',
            'measure_run': rotor.measure_run or '',
            'balancing_run': rotor.balancing_run or '',
            'rpm': rotor.rpm or '',
            'plane1_weight': rotor.plane1_weight,
            'plane1_degree': rotor.plane1_degree,
            'plane2_weight': rotor.plane2_weight,
            'plane2_degree': rotor.plane2_degree,
            'recorded_at': rotor.recorded_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if rotor.recorded_at else '',
            'imported_at': rotor.imported_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if rotor.imported_at else '',
        }
        
    # Stator Balancing
    stator = StatorBalancingRecord.objects.filter(serial_number__iexact=serial).first()
    if stator:
        response_data['stator_balancing'] = {
            'id': stator.id,
            'serial_number': stator.serial_number,
            'final_result': stator.final_result,
            'ry': stator.ry or '',
            'ry_result': stator.ry_result or '',
            'surge_voltage': stator.surge_voltage or '',
            'recorded_at': stator.recorded_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if stator.recorded_at else '',
            'imported_at': stator.imported_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if stator.imported_at else '',
        }
        
    if not response_data:
        return Response({'detail': 'No Record Found'}, status=404)
        
    return Response(response_data)


# ══════════════════════════════════════════════════════════════════════════════
# PARTS API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
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
def api_check_serial(request):
    serial = request.query_params.get('serial', '').strip().upper()
    if not serial:
        return Response({'detail': 'serial is required'}, status=400)
    exists = Serial.objects.filter(serial_number=serial).exists()
    return Response({'exists': exists})


@api_view(['POST'])
def api_add_part(request):
    serial_number = request.data.get('serial_number', '')
    part_number = request.data.get('part_number', '')
    part_name = request.data.get('part_name', '')
    line_no = request.data.get('line_no', '')
    shift_val = request.data.get('shift', '')

    if not part_number.isdigit() or len(part_number) != 5:
        return Response({'detail': 'Part number must be exactly 5 digits'}, status=400)
    if not part_name:
        return Response({'detail': 'Part name is required'}, status=400)
    if not line_no.isdigit() or len(line_no) != 2:
        return Response({'detail': 'Line number must be 2 digits (e.g. 01)'}, status=400)
    if shift_val.upper() not in ('A', 'B', 'C', 'G'):
        return Response({'detail': 'Shift must be A, B, C, or G'}, status=400)

    if Part.objects.filter(serial_number=serial_number).exists():
        return Response({'detail': 'Serial number already exists.'}, status=400)

    user = request.user
    full_name = user.get_full_name() or user.username if user.is_authenticated else ''

    try:
        new_part = Part.objects.create(
            serial_number=serial_number,
            part_number=part_number,
            part_name=part_name,
            line_no=line_no,
            shift=shift_val.upper(),
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
    except Exception as e:
        return Response({'detail': f'Database error: {e}'}, status=500)


@api_view(['GET'])
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
def api_delete_part(request, part_id):
    try:
        part = Part.objects.get(id=part_id)
    except Part.DoesNotExist:
        return Response({'detail': 'Part not found'}, status=404)

    part.delete()
    return Response({'status': 'deleted'})


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTION LOG API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
def api_production_log(request):
    """Return 7-day aggregated production data."""
    part_type = request.query_params.get('part_type', '')
    today = date.today()
    start_date = today - timedelta(days=6)

    qs = Serial.objects.filter(created_at__date__gte=start_date)
    if part_type:
        qs = qs.filter(part_type=part_type)
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
        d = s.created_at.strftime('%Y-%m-%d')
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
def api_production_log_day(request):
    """Return individual serial records for a specific date."""
    day = request.query_params.get('day', '')
    part_type = request.query_params.get('part_type', '')

    qs = Serial.objects.filter(created_at__date=day)
    if part_type:
        qs = qs.filter(part_type=part_type)
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
            'rotor_result': getattr(RotorBalancing.objects.filter(serial_number=s.serial_number).first(), 'result', None)
        })

    return Response({
        'date': day,
        'total': len(records),
        'marked': marked,
        'pending': len(records) - marked,
        'shifts': shift_counts,
        'records': records,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ROTOR BALANCING API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['POST'])
def api_rotor_balancing_import(request):
    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response({'detail': 'No file uploaded'}, status=400)

    try:
        wb = openpyxl.load_workbook(file_obj, data_only=True)
        sheet = wb.active
        
        # Read header to find column indices
        headers = []
        for cell in sheet[1]:
            headers.append(str(cell.value).strip() if cell.value else '')
            
        try:
            req_cols = ['dd-mm-yy', 'hh:mm:ss', 'Rotor-Type', 'Rotor-Ident', 'Mea-Run', 'Bal-Run', 'RpM', 'PL1[G_MM]', 'PL1[DEG]', 'PL2[G_MM]', 'PL2[DEG]', 'InTol']
            col_indices = {col: headers.index(col) for col in req_cols}
        except ValueError as e:
            return Response({'detail': f'Missing expected column: {e}'}, status=400)

        imported = 0
        skipped = 0
        
        def safe_int(val):
            try: return int(float(val)) if val is not None else None
            except: return None
            
        def safe_float(val):
            try: return float(val) if val is not None else None
            except: return None

        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row: continue
            sn_val = row[col_indices['Rotor-Ident']]
            if not sn_val: continue
                
            serial_num = str(sn_val).strip()
            result_val = str(row[col_indices['InTol']]).strip().upper()
            rotor_type_val = str(row[col_indices['Rotor-Type']] or '').strip()
            
            # recorded_at
            date_val = row[col_indices['dd-mm-yy']]
            time_val = row[col_indices['hh:mm:ss']]
            recorded_at = None
            try:
                if isinstance(date_val, dt.datetime):
                    if isinstance(time_val, dt.time):
                        recorded_at = dt.datetime.combine(date_val.date(), time_val)
                    else:
                        recorded_at = date_val
                elif isinstance(date_val, str) and isinstance(time_val, str):
                    date_str, time_str = date_val.strip(), time_val.strip()
                    if date_str and time_str:
                        dt_str = f"{date_str} {time_str}"
                        for fmt in ("%d-%m-%y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                            try:
                                recorded_at = dt.datetime.strptime(dt_str, fmt)
                                break
                            except ValueError:
                                pass
                if recorded_at and django_tz.is_naive(recorded_at):
                    recorded_at = django_tz.make_aware(recorded_at)
            except Exception:
                pass

            final_res = 'Pass' if result_val == 'Y' else 'Fail'

            if RotorBalancing.objects.filter(serial_number=serial_num).exists():
                skipped += 1
            else:
                RotorBalancing.objects.create(
                    serial_number=serial_num,
                    result=final_res,
                    rotor_type=rotor_type_val,
                    recorded_at=recorded_at,
                    measure_run=safe_int(row[col_indices['Mea-Run']]),
                    balancing_run=safe_int(row[col_indices['Bal-Run']]),
                    rpm=safe_int(row[col_indices['RpM']]),
                    plane1_weight=safe_float(row[col_indices['PL1[G_MM]']]),
                    plane1_degree=safe_float(row[col_indices['PL1[DEG]']]),
                    plane2_weight=safe_float(row[col_indices['PL2[G_MM]']]),
                    plane2_degree=safe_float(row[col_indices['PL2[DEG]']])
                )
                imported += 1
                
        return Response({'detail': f'{imported} records imported, {skipped} skipped (already existed).'})

    except Exception as e:
        return Response({'detail': f'Error parsing file: {str(e)}'}, status=500)


@api_view(['GET'])
def api_rotor_balancing_list(request):
    records = RotorBalancing.objects.all().order_by('-imported_at')[:200]
    data = []
    for r in records:
        data.append({
            'id': r.id,
            'serial_number': r.serial_number,
            'result': r.result,
            'rotor_type': r.rotor_type or '',
            'measure_run': r.measure_run or '',
            'balancing_run': r.balancing_run or '',
            'rpm': r.rpm or '',
            'plane1_weight': r.plane1_weight if r.plane1_weight is not None else '',
            'plane1_degree': r.plane1_degree if r.plane1_degree is not None else '',
            'plane2_weight': r.plane2_weight if r.plane2_weight is not None else '',
            'plane2_degree': r.plane2_degree if r.plane2_degree is not None else '',
            'recorded_at': r.recorded_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if r.recorded_at else '',
            'imported_at': r.imported_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if r.imported_at else ''
        })
    return Response(data)

@api_view(['DELETE'])
def api_rotor_balancing_delete(request, pk):
    try:
        record = RotorBalancing.objects.get(pk=pk)
        record.delete()
        return Response({'success': True})
    except RotorBalancing.DoesNotExist:
        return Response({'success': False, 'error': 'Record not found'}, status=404)


# ══════════════════════════════════════════════════════════════════════════════
# STATOR BALANCING API
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['POST'])
def api_stator_balancing_import(request):
    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response({'detail': 'No file uploaded'}, status=400)

    try:
        df = pd.read_csv(file_obj, sep='\t')
        
        req_cols = ['BAR CODE', 'DATE', 'FINAL RESULT', 'R/Y', 'R/Y RESULT', 'SURGE VOLTAGE']
        missing = [c for c in req_cols if c not in df.columns]
        if missing:
            return Response({'detail': f'Missing expected columns: {", ".join(missing)}'}, status=400)

        imported = 0
        skipped = 0

        for index, row in df.iterrows():
            sn_val = str(row['BAR CODE']).strip()
            if not sn_val or sn_val == 'nan': 
                continue
                
            if StatorBalancingRecord.objects.filter(serial_number=sn_val).exists():
                skipped += 1
                continue

            date_val = row['DATE']
            recorded_at = None
            if pd.notna(date_val):
                try:
                    row_dt = pd.to_datetime(date_val)
                    if row_dt.tzinfo is None:
                        row_dt = row_dt.tz_localize('UTC').astimezone(IST)
                    recorded_at = row_dt.to_pydatetime()
                except Exception:
                    pass

            ry_val = str(row['R/Y']).strip() if pd.notna(row['R/Y']) else ''
            ry_result_val = str(row['R/Y RESULT']).strip() if pd.notna(row['R/Y RESULT']) else ''
            surge_val = str(row['SURGE VOLTAGE']).strip() if pd.notna(row['SURGE VOLTAGE']) else ''
            final_res = str(row['FINAL RESULT']).strip()

            StatorBalancingRecord.objects.create(
                serial_number=sn_val,
                recorded_at=recorded_at,
                final_result=final_res,
                ry=ry_val,
                ry_result=ry_result_val,
                surge_voltage=surge_val
            )
            imported += 1

        return Response({'detail': f'{imported} records imported, {skipped} skipped (already existed).'})

    except Exception as e:
        return Response({'detail': f'Error parsing TSV file: {str(e)}'}, status=500)


@api_view(['GET'])
def api_stator_balancing_list(request):
    records = StatorBalancingRecord.objects.all().order_by('-imported_at')[:200]
    data = []
    for r in records:
        data.append({
            'id': r.id,
            'serial_number': r.serial_number,
            'recorded_at': r.recorded_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if r.recorded_at else '',
            'final_result': r.final_result,
            'ry': r.ry or '',
            'ry_result': r.ry_result or '',
            'surge_voltage': r.surge_voltage or '',
            'imported_at': r.imported_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') if r.imported_at else ''
        })
    return Response(data)

@api_view(['DELETE'])
def api_stator_balancing_delete(request, pk):
    try:
        record = StatorBalancingRecord.objects.get(pk=pk)
        record.delete()
        return Response({'success': True})
    except StatorBalancingRecord.DoesNotExist:
        return Response({'success': False, 'error': 'Record not found'}, status=404)
