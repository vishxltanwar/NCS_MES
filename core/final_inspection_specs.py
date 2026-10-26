"""Canonical Final Inspection parameter catalogue.

Limits follow the EVR185 checksheet.  Only parameters with real limits carry
spec_min/spec_max; informational columns stay unbounded.
"""

PARAMETER_SPECS = [
    # Mechanical
    {'code': 'MECHANICAL_SHAFT_RUNOUT', 'name': 'Shaft runout', 'section': 'Mechanical',
     'unit': 'mm', 'spec_max': 0.05, 'spec_text': '0.050 max'},
    {'code': 'MECHANICAL_PARALLELISM', 'name': 'Shaft face / front top fit face parallelism',
     'section': 'Mechanical', 'unit': 'mm', 'spec_max': 0.05, 'spec_text': '0.050 max'},

    # Encoder signals
    {'code': 'ENC_SIN_MIN', 'name': 'Sin min', 'section': 'Encoder signals',
     'unit': 'V', 'spec_min': 1.3, 'spec_max': 1.5},
    {'code': 'ENC_SIN_MAX', 'name': 'Sin max', 'section': 'Encoder signals',
     'unit': 'V', 'spec_min': 3.5, 'spec_max': 3.7},
    {'code': 'ENC_COS_MIN', 'name': 'Cos min', 'section': 'Encoder signals',
     'unit': 'V', 'spec_min': 1.3, 'spec_max': 1.5},
    {'code': 'ENC_COS_MAX', 'name': 'Cos max', 'section': 'Encoder signals',
     'unit': 'V', 'spec_min': 3.5, 'spec_max': 3.7},

    # Thermal
    {'code': 'THERMAL_SHAFT_TEMP', 'name': 'Shaft temp after 5 min @7000 RPM',
     'section': 'Thermal', 'unit': 'C', 'spec_max': 75},
    {'code': 'THERMAL_COIL1', 'name': 'Coil temp 1', 'section': 'Thermal',
     'unit': 'C', 'spec_max': 85},
    {'code': 'THERMAL_COIL2', 'name': 'Coil temp 2', 'section': 'Thermal',
     'unit': 'C', 'spec_max': 85},
    {'code': 'THERMAL_BODY_TEMP', 'name': 'Body temp', 'section': 'Thermal',
     'unit': 'C', 'spec_max': 85},

    # Encoder angle
    {'code': 'ENC_ANGLE_RAD', 'name': 'Encoder angle', 'section': 'Encoder angle',
     'unit': 'rad', 'spec_text': 'raw'},
    {'code': 'ENC_ANGLE_DEG', 'name': 'Encoder angle', 'section': 'Encoder angle',
     'unit': 'deg', 'spec_max': 360, 'is_calculated': True},
    {'code': 'ENC_ANGLE_VALUE', 'name': 'Encoder angle value', 'section': 'Encoder angle',
     'unit': '', 'spec_max': 3600, 'is_calculated': True},

    # BEMF
    {'code': 'BEMF_BEFORE', 'name': 'BEMF before', 'section': 'BEMF',
     'unit': '%', 'spec_min': 10},
    {'code': 'BEMF_HOT', 'name': 'BEMF hot', 'section': 'BEMF', 'unit': '%'},
    {'code': 'BEMF_AFTER', 'name': 'BEMF after (cool)', 'section': 'BEMF', 'unit': '%'},

    # Thermistor
    {'code': 'THERMISTOR1', 'name': 'Thermistor 1', 'section': 'Thermistor', 'unit': 'C'},
    {'code': 'THERMISTOR2', 'name': 'Thermistor 2', 'section': 'Thermistor', 'unit': 'C'},
    {'code': 'THERMISTOR_MISMATCH', 'name': 'Thermistor 2 vs 1 mismatch',
     'section': 'Thermistor', 'unit': '%', 'spec_min': -1, 'spec_max': 1,
     'is_calculated': True},

    # Motor resistance
    {'code': 'RES_R1', 'name': 'Resistance R1', 'section': 'Motor resistance',
     'unit': 'mOhm', 'spec_min': 7.35, 'spec_max': 8.45},
    {'code': 'RES_R2', 'name': 'Resistance R2', 'section': 'Motor resistance',
     'unit': 'mOhm', 'spec_min': 7.35, 'spec_max': 8.45},
    {'code': 'RES_R3', 'name': 'Resistance R3', 'section': 'Motor resistance',
     'unit': 'mOhm', 'spec_min': 7.35, 'spec_max': 8.45},

    # IR / HV
    {'code': 'IR_MOHM', 'name': 'IR', 'section': 'IR / HV leakage',
     'unit': 'MOhm', 'spec_min': 100, 'spec_text': '>100 MOhm @1000 VDC / 60 s'},
    {'code': 'HV_MA', 'name': 'HV leakage', 'section': 'IR / HV leakage',
     'unit': 'mA', 'spec_max': 5, 'spec_text': '5 mA max @1500 VAC / 10 s'},

    # Noise
    {'code': 'NOISE_1000', 'name': 'Noise @1000 RPM', 'section': 'Noise dB',
     'unit': 'dB', 'spec_max': 56},
    {'code': 'NOISE_2000', 'name': 'Noise @2000 RPM', 'section': 'Noise dB',
     'unit': 'dB', 'spec_max': 60},
    {'code': 'NOISE_3000', 'name': 'Noise @3000 RPM', 'section': 'Noise dB',
     'unit': 'dB', 'spec_max': 64},
    {'code': 'NOISE_4000', 'name': 'Noise @4000 RPM', 'section': 'Noise dB',
     'unit': 'dB', 'spec_max': 68},
    {'code': 'NOISE_5000', 'name': 'Noise @5000 RPM', 'section': 'Noise dB',
     'unit': 'dB', 'spec_max': 68.5},
    {'code': 'NOISE_6000', 'name': 'Noise @6000 RPM', 'section': 'Noise dB',
     'unit': 'dB', 'spec_max': 75.5},
    {'code': 'NOISE_7000', 'name': 'Noise @7000 RPM', 'section': 'Noise dB',
     'unit': 'dB', 'spec_max': 81},

    # Dimensions
    {'code': 'DIM_MAGNET_HEIGHT', 'name': 'Encoder magnet height',
     'section': 'Dimensions', 'unit': 'mm', 'spec_min': 6.7, 'spec_max': 6.9},
    {'code': 'DIM_PCB_HEIGHT', 'name': 'PCB height', 'section': 'Dimensions',
     'unit': 'mm', 'spec_min': 2.3, 'spec_max': 3.3},

    # 4Q bench
    {'code': 'FOURQ_LOSS_500', 'name': 'Open circuit loss @500 RPM',
     'section': '4Q bench', 'unit': 'W', 'spec_max': 20},
    {'code': 'FOURQ_LOSS_5K', 'name': 'Open circuit loss @5000 RPM',
     'section': '4Q bench', 'unit': 'W', 'spec_max': 400},
    {'code': 'FOURQ_LOSS_10K', 'name': 'Open circuit loss @10000 RPM',
     'section': '4Q bench', 'unit': 'W', 'spec_max': 1200},
    {'code': 'EFFICIENCY', 'name': 'Efficiency', 'section': '4Q bench',
     'unit': '%', 'spec_min': 91},
    {'code': 'FOURQ_PEAK_TORQUE', 'name': 'Peak torque @500 RPM',
     'section': '4Q bench', 'unit': 'Nm', 'spec_min': 56},

    # Final BEMF / vibration
    {'code': 'BEMF_UV', 'name': 'BEMF 1k RPM CW UV', 'section': 'Final assy BEMF',
     'unit': 'V'},
    {'code': 'BEMF_VW', 'name': 'BEMF 1k RPM CW VW', 'section': 'Final assy BEMF',
     'unit': 'V'},
    {'code': 'BEMF_WU', 'name': 'BEMF 1k RPM CW WU', 'section': 'Final assy BEMF',
     'unit': 'V'},
    {'code': 'VIBRATION', 'name': 'Vibration', 'section': 'Final assy BEMF',
     'unit': 'mm/s'},
]

for _order, _spec in enumerate(PARAMETER_SPECS, start=1):
    _spec.setdefault('spec_min', None)
    _spec.setdefault('spec_max', None)
    _spec.setdefault('spec_text', '')
    _spec.setdefault('unit', '')
    _spec.setdefault('input_type', 'Float')
    _spec.setdefault('is_calculated', False)
    _spec['sort_order'] = _order

PARAMETER_BY_CODE = {spec['code']: spec for spec in PARAMETER_SPECS}
PARAMETER_CODES = [spec['code'] for spec in PARAMETER_SPECS]
CALCULATED_CODES = {spec['code'] for spec in PARAMETER_SPECS if spec['is_calculated']}
