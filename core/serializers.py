"""DRF serializers for Final Inspection."""
from rest_framework import serializers
from .models import FinalInspection, FinalInspectionParameter, FinalInspectionReading


class FinalInspectionParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinalInspectionParameter
        fields = ['id', 'code', 'name', 'section', 'unit', 'spec_min', 'spec_max',
                  'spec_text', 'input_type', 'is_calculated', 'sort_order', 'active']


class FinalInspectionReadingSerializer(serializers.ModelSerializer):
    parameter = FinalInspectionParameterSerializer(read_only=True)
    class Meta:
        model = FinalInspectionReading
        fields = ['id', 'parameter', 'value', 'result']


class FinalInspectionSerializer(serializers.ModelSerializer):
    readings = FinalInspectionReadingSerializer(many=True, read_only=True)
    inspector_full_name = serializers.CharField(source='inspector.get_full_name', read_only=True)
    class Meta:
        model = FinalInspection
        fields = ['id', 'motor_serial', 'enc_no', 'stator_serial', 'rotor_serial',
                  'magnet_type', 'pcb_board', 'inspector', 'inspector_full_name',
                  'inspected_at', 'attempt_no', 'status', 'overall_result',
                  'remarks', 'completed_at', 'readings']
