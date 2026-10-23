from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from rest_framework.response import Response


ROLE_ADMIN = 'admin'
ROLE_SUPERVISOR = 'supervisor'
ROLE_OPERATOR = 'operator'
ROLE_VIEWER = 'viewer'

STATION_LASER_MARKING = 'laser_marking'
STATION_ROTOR_BALANCING = 'rotor_balancing'
STATION_STATOR_TESTING = 'stator_testing'
STATION_MAGNET_INSERTION = 'magnet_insertion'
STATION_MOTOR_ASSEMBLY = 'motor_assembly'
STATION_FINAL_INSPECTION = 'final_inspection'
STATION_DISPATCH = 'dispatch'

ROLE_CHOICES = [
    (ROLE_ADMIN, 'Admin'),
    (ROLE_SUPERVISOR, 'Supervisor'),
    (ROLE_OPERATOR, 'Operator'),
    (ROLE_VIEWER, 'Viewer'),
]

STATION_CHOICES = [
    ('', 'No station'),
    (STATION_LASER_MARKING, 'Laser Marking'),
    (STATION_ROTOR_BALANCING, 'Rotor Balancing'),
    (STATION_STATOR_TESTING, 'Stator Testing'),
    (STATION_MAGNET_INSERTION, 'Magnet Insertion'),
    (STATION_MOTOR_ASSEMBLY, 'Motor Assembly'),
    (STATION_FINAL_INSPECTION, 'Final Inspection'),
    (STATION_DISPATCH, 'Dispatch'),
]

PAGE_URLS = {
    'dashboard': '/dashboard',
    'laser': '/laser-marking',
    'add_part': '/add-part',
    'trace': '/traceability',
    'motor_traceability': '/traceability/motor',
    'machine_overview': '/machine-overview',
    'shift': '/shift-report',
    'production_log': '/production-log',
    'rotor_balancing': '/rotor-balancing',
    'magnet_insertion': '/magnet-insertion',
    'stator_testing': '/stator-testing',
    'motor_assembly': '/motor-assembly',
    'rotor_operations': '/rotor-operations',
    'front_plate_bearing_assy': '/front-plate-bearing-assy',
    'front_plate_rotor_assy': '/front-plate-rotor-assy',
    'stator_op120': '/stator-op120',
    'motor_operations': '/motor-operations',
    'motor_marking': '/motor-marking',
    'final_inspection': '/final-inspection',
    'dispatch_release': '/dispatch-release',
}

PAGE_STATIONS = {
    'laser': STATION_LASER_MARKING,
    'rotor_balancing': STATION_ROTOR_BALANCING,
    'stator_testing': STATION_STATOR_TESTING,
    'magnet_insertion': STATION_MAGNET_INSERTION,
    'rotor_operations': STATION_ROTOR_BALANCING,
    'front_plate_bearing_assy': STATION_ROTOR_BALANCING,
    'front_plate_rotor_assy': STATION_ROTOR_BALANCING,
    'stator_op120': STATION_STATOR_TESTING,
    'motor_operations': STATION_MOTOR_ASSEMBLY,
    'motor_marking': STATION_MOTOR_ASSEMBLY,
    'final_inspection': STATION_FINAL_INSPECTION,
    'dispatch_release': STATION_DISPATCH,
}

ADMIN_PAGES = set(PAGE_URLS)
SUPERVISOR_PAGES = {
    'dashboard',
    'trace',
    'motor_traceability',
    'machine_overview',
    'shift',
    'production_log',
    'laser',
    'rotor_balancing',
    'stator_testing',
    'magnet_insertion',
    'rotor_operations',
    'front_plate_bearing_assy',
    'front_plate_rotor_assy',
    'stator_op120',
    'motor_operations',
    'motor_marking',
    'final_inspection',
    'dispatch_release',
    'motor_assembly',
}
VIEWER_PAGES = {
    'dashboard',
    'trace',
    'motor_traceability',
}

READ_ACTIONS = {
    'stats',
    'serials_read',
    'laser_read',
    'traceability_read',
    'part_lookup',
    'parts_read',
    'production_log_read',
    'rotor_read',
    'stator_read',
    'motor_assembly_read',
    'magnet_read',
    'rotor_operations_read',
    'stator_op120_read',
    'motor_operations_read',
    'motor_marking_read',
    'final_inspection_read',
    'dispatch_read',
}

VIEWER_READ_ACTIONS = {
    'stats',
    'traceability_read',
}

ADMIN_ONLY_ACTIONS = {
    'add_part_write',
    'part_delete',
    'serial_delete',
    'motor_assembly_write',
}

STATION_ACTIONS = {
    'laser_write': STATION_LASER_MARKING,
    'mark_done': STATION_LASER_MARKING,
    'rotor_write': STATION_ROTOR_BALANCING,
    'stator_write': STATION_STATOR_TESTING,
    'magnet_write': STATION_MAGNET_INSERTION,
    'yoke_shaft_write': STATION_ROTOR_BALANCING,
    'rotor_op70_write': STATION_ROTOR_BALANCING,
    'rotor_op80_write': STATION_ROTOR_BALANCING,
    'rotor_release_write': STATION_ROTOR_BALANCING,
    'stator_op120_write': STATION_STATOR_TESTING,
    'stator_release_write': STATION_STATOR_TESTING,
    'motor_op10_write': STATION_MOTOR_ASSEMBLY,
    'motor_op70_write': STATION_MOTOR_ASSEMBLY,
    'motor_op90_write': STATION_MOTOR_ASSEMBLY,
    'motor_op100_write': STATION_MOTOR_ASSEMBLY,
    'motor_serial_assign_write': STATION_MOTOR_ASSEMBLY,
    'motor_op120_write': STATION_MOTOR_ASSEMBLY,
    'final_inspection_write': STATION_FINAL_INSPECTION,
    'dispatch_write': STATION_DISPATCH,
}

READ_ACTION_STATIONS = {
    'serials_read': STATION_LASER_MARKING,
    'laser_read': STATION_LASER_MARKING,
    'part_lookup': STATION_LASER_MARKING,
    'rotor_read': STATION_ROTOR_BALANCING,
    'stator_read': STATION_STATOR_TESTING,
    'magnet_read': STATION_MAGNET_INSERTION,
    'rotor_operations_read': STATION_ROTOR_BALANCING,
    'stator_op120_read': STATION_STATOR_TESTING,
    'motor_operations_read': STATION_MOTOR_ASSEMBLY,
    'motor_marking_read': STATION_MOTOR_ASSEMBLY,
    'final_inspection_read': STATION_FINAL_INSPECTION,
    'dispatch_read': STATION_DISPATCH,
}


def user_profile(user):
    if not user or not user.is_authenticated:
        return None
    return getattr(user, 'profile', None)


def user_role(user):
    if not user or not user.is_authenticated:
        return ''
    profile = user_profile(user)
    if profile:
        return getattr(profile, 'role', ROLE_VIEWER) or ROLE_VIEWER
    if user.is_superuser:
        return ROLE_ADMIN
    return ROLE_VIEWER


def user_station(user):
    profile = user_profile(user)
    return getattr(profile, 'station', '') if profile else ''


def can_access_page(user, page):
    role = user_role(user)
    if role == ROLE_ADMIN:
        return page in ADMIN_PAGES
    if role == ROLE_SUPERVISOR:
        return page in SUPERVISOR_PAGES
    if role == ROLE_VIEWER:
        return page in VIEWER_PAGES
    if role == ROLE_OPERATOR:
        return PAGE_STATIONS.get(page) == user_station(user)
    return False


def can_access_action(user, action):
    role = user_role(user)
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_VIEWER:
        return action in VIEWER_READ_ACTIONS
    if role == ROLE_SUPERVISOR:
        return action in READ_ACTIONS
    if role == ROLE_OPERATOR:
        station = user_station(user)
        if action in READ_ACTIONS:
            return READ_ACTION_STATIONS.get(action) == station
        return STATION_ACTIONS.get(action) == station
    return False


def allowed_pages(user):
    return {page: can_access_page(user, page) for page in PAGE_URLS}


def first_allowed_url(user):
    preferred_order = [
        'dashboard',
        'laser',
        'rotor_balancing',
        'stator_testing',
        'magnet_insertion',
        'trace',
        'production_log',
    ]
    for page in preferred_order:
        if can_access_page(user, page):
            return PAGE_URLS[page]
    for page, url in PAGE_URLS.items():
        if can_access_page(user, page):
            return url
    return None


def page_access_required(page):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if can_access_page(request.user, page):
                return view_func(request, *args, **kwargs)
            fallback_url = first_allowed_url(request.user)
            if fallback_url and request.path != fallback_url:
                return redirect(fallback_url)
            raise PermissionDenied
        return wrapped
    return decorator


def api_access_required(action):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if can_access_action(request.user, action):
                return view_func(request, *args, **kwargs)
            return Response({'detail': 'You do not have permission to perform this action.'}, status=403)
        return wrapped
    return decorator
