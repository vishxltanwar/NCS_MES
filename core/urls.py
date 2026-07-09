# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ── Page routes ───────────────────────────────────────────────────────────
    path('', views.root_view, name='root'),
    path('dashboard', views.dashboard_view, name='dashboard'),
    path('laser-marking', views.laser_marking_view, name='laser_marking'),
    path('add-part', views.add_part_view, name='add_part'),
    path('traceability', views.traceability_view, name='traceability'),
    path('machine-overview', views.machine_overview_view, name='machine_overview'),
    path('shift-report', views.shift_report_view, name='shift_report'),
    path('production-log', views.production_log_view, name='production_log'),
    path('rotor-balancing', views.rotor_balancing_view, name='rotor_balancing'),
    path('magnet-insertion', views.magnet_insertion_view, name='magnet_insertion'),
    path('stator-testing', views.stator_testing_view, name='stator_testing'),
    path('motor-assembly', views.motor_assembly_view, name='motor_assembly'),

    # ── Auth API ──────────────────────────────────────────────────────────────
    path('api/login', views.api_login, name='api_login'),
    path('api/logout', views.api_logout, name='api_logout'),

    # ── Serial API ────────────────────────────────────────────────────────────
    path('api/generate', views.api_generate, name='api_generate'),
    path('api/serials', views.api_serials, name='api_serials'),
    path('api/serials/<int:serial_id>', views.api_delete_serial, name='api_delete_serial'),
    path('api/traceability/search/', views.api_traceability_search, name='api_traceability_search'),
    path('api/mark-done', views.api_mark_done, name='api_mark_done'),
    path('api/stats', views.api_stats, name='api_stats'),

    # ── Parts API ─────────────────────────────────────────────────────────────
    path('api/part-lookup/', views.api_part_lookup, name='api_part_lookup'),
    path('api/check-serial/', views.api_check_serial, name='api_check_serial'),
    path('api/add-part', views.api_add_part, name='api_add_part'),
    path('api/parts', views.api_parts, name='api_parts'),
    path('api/parts/<int:part_id>', views.api_delete_part, name='api_delete_part'),

    # ── Production Log API ────────────────────────────────────────────────────
    path('api/production-log', views.api_production_log, name='api_production_log'),
    path('api/production-log/day', views.api_production_log_day, name='api_production_log_day'),

    # ── Rotor Balancing API ───────────────────────────────────────────────────
    path('api/rotor-balancing/import/', views.api_rotor_balancing_import, name='api_rotor_balancing_import'),
    path('api/rotor-balancing/', views.api_rotor_balancing_list, name='api_rotor_balancing_list'),
    path('api/rotor-balancing/<int:pk>/', views.api_rotor_balancing_delete, name='api_rotor_balancing_delete'),

    # ── Stator Testing API ───────────────────────────────────────────────────
    path('api/stator-testing/import/', views.api_stator_testing_import, name='api_stator_testing_import'),
    path('api/stator-testing/', views.api_stator_testing_list, name='api_stator_testing_list'),
    path('api/stator-testing/<int:pk>/', views.api_stator_testing_delete, name='api_stator_testing_delete'),

    # Motor Assembly API
    path('api/machines/motor-assembly/', views.api_motor_assembly, name='api_motor_assembly'),

    # ── Magnet Insertion API ──────────────────────────────────────────────────
    path('api/magnet-insertion/status/', views.api_magnet_insertion_status, name='api_magnet_insertion_status'),
    path('api/magnet-insertion/', views.api_magnet_insertion_list, name='api_magnet_insertion_list'),
    path('api/magnet-insertion/create/', views.api_magnet_insertion_create, name='api_magnet_insertion_create'),
    path('api/magnet-insertion/stats/', views.api_magnet_insertion_stats, name='api_magnet_insertion_stats'),
    path('api/magnet-insertion/<int:pk>/', views.api_magnet_insertion_delete, name='api_magnet_insertion_delete'),
]
