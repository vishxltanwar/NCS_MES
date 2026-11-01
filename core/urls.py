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
    path('traceability/motor', views.motor_traceability_view, name='motor_traceability'),
    path('motor-traceability/<str:motor_sr_no>/pdf/', views.motor_traceability_pdf_view, name='motor_traceability_pdf'),
    path('machine-overview', views.machine_overview_view, name='machine_overview'),
    path('shift-report', views.shift_report_view, name='shift_report'),
    path('production-log', views.production_log_view, name='production_log'),
    path('rotor-balancing', views.rotor_balancing_view, name='rotor_balancing'),
    path('rotor-operations', views.rotor_operations_view, name='rotor_operations'),
    path('front-plate-bearing-assy', views.front_plate_bearing_assy_view, name='front_plate_bearing_assy'),
    path('front-plate-rotor-assy', views.front_plate_rotor_assy_view, name='front_plate_rotor_assy'),
    path('magnet-insertion', views.magnet_insertion_view, name='magnet_insertion'),
    path('stator-testing', views.stator_testing_view, name='stator_testing'),
    path('motor-assembly', views.motor_assembly_view, name='motor_assembly'),
    path('eol-testing', views.eol_testing_view, name='eol_testing'),
    path('final-inspection', views.final_inspection_view, name='final_inspection'),
    path('final-inspection/records', views.final_inspection_records_view, name='final_inspection_records'),
    path('final-inspection/records/<int:pk>', views.final_inspection_record_detail_view, name='final_inspection_record_detail'),
    path('dispatch-release', views.dispatch_release_view, name='dispatch_release'),
    path('noise-test', views.noise_test_view, name='noise'),
    path('final-testing', views.eol_testing_4q_view, name='eol_testing_4q'),
    path('pre-delivery-inspection', views.pre_delivery_inspection_view, name='pre_delivery_inspection'),

    # ── Auth API ──────────────────────────────────────────────────────────────
    path('api/login', views.api_login, name='api_login'),
    path('api/logout', views.api_logout, name='api_logout'),

    # ── Serial API ────────────────────────────────────────────────────────────
    path('api/generate', views.api_generate, name='api_generate'),
    path('api/serials', views.api_serials, name='api_serials'),
    path('api/serials/<int:serial_id>', views.api_delete_serial, name='api_delete_serial'),
    path('api/serials/<int:serial_id>/retry-delivery', views.api_retry_serial_delivery, name='api_retry_serial_delivery'),
    path('api/scanner/poll/', views.api_scanner_poll, name='api_scanner_poll'),
    path('api/traceability/search/', views.api_traceability_search, name='api_traceability_search'),
    path('api/traceability/motor/<str:serial>/', views.api_motor_traceability, name='api_motor_traceability'),
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
    path('api/rotor-balancing/by-serial/<str:serial>/', views.api_rotor_balancing_by_serial, name='api_rotor_balancing_by_serial'),
    path('api/rotor-balancing/<int:pk>/', views.api_rotor_balancing_delete, name='api_rotor_balancing_delete'),

    # ── Stator Testing API ───────────────────────────────────────────────────
    path('api/stator-testing/import/', views.api_stator_testing_import, name='api_stator_testing_import'),
    path('api/stator-testing/', views.api_stator_testing_list, name='api_stator_testing_list'),
    path('api/stator-testing/by-serial/<str:serial>/', views.api_stator_testing_by_serial, name='api_stator_testing_by_serial'),
    path('api/stator-testing/<int:pk>/', views.api_stator_testing_delete, name='api_stator_testing_delete'),

    # Motor Assembly API
    path('api/machines/motor-assembly/', views.api_motor_assembly, name='api_motor_assembly'),
    path('api/machines/motor-assembly/<int:pk>/assign-serial/', views.api_motor_serial_assign, name='api_motor_serial_assign'),

    # ── Operations API ────────────────────────────────────────────────────────
    path('api/operations/', views.api_operations_list, name='api_operations_list'),
    path('api/operations/record/', views.api_operation_record, name='api_operation_record'),
    path('api/operations/check-sequence/', views.api_operation_check_sequence, name='api_operation_check_sequence'),
    path('api/operations/by-serial/<str:entity_type>/<str:serial>/', views.api_operations_by_serial, name='api_operations_by_serial'),

    # ── Magnet Insertion API ──────────────────────────────────────────────────
    path('api/magnet-insertion/status/', views.api_magnet_insertion_status, name='api_magnet_insertion_status'),
    path('api/magnet-insertion/cycle/save/', views.api_magnet_insertion_cycle_save, name='api_magnet_insertion_cycle_save'),
    path('api/magnet-insertion/reset/', views.api_magnet_insertion_reset, name='api_magnet_insertion_reset'),
    path('api/magnet-insertion/', views.api_magnet_insertion_list, name='api_magnet_insertion_list'),
    path('api/magnet-insertion/create/', views.api_magnet_insertion_create, name='api_magnet_insertion_create'),
    path('api/magnet-insertion/stats/', views.api_magnet_insertion_stats, name='api_magnet_insertion_stats'),
    path('api/magnet-insertion/<int:pk>/', views.api_magnet_insertion_delete, name='api_magnet_insertion_delete'),
    # ── Final Inspection API ──────────────────────────────────────────────
    path('api/final-inspection/', views.api_final_inspection_list, name='api_final_inspection_list'),
    path('api/final-inspection/parameters/', views.api_final_inspection_parameters, name='api_final_inspection_parameters'),
    path('api/final-inspection/export/', views.api_final_inspection_export_list, name='api_final_inspection_export_list'),
    path('api/final-inspection/assembly-lookup/<str:serial>/', views.api_final_inspection_assembly_lookup, name='api_final_inspection_assembly_lookup'),
    path('api/final-inspection/by-serial/<str:serial>/', views.api_final_inspection_by_serial, name='api_final_inspection_by_serial'),
    path('api/final-inspection/<int:pk>/', views.api_final_inspection_detail, name='api_final_inspection_detail'),
    path('api/final-inspection/<int:pk>/update/', views.api_final_inspection_update, name='api_final_inspection_update'),
    path('api/final-inspection/<int:pk>/complete/', views.api_final_inspection_complete, name='api_final_inspection_complete'),
    path('api/final-inspection/<int:pk>/export/', views.api_final_inspection_export, name='api_final_inspection_export'),
]
