import ast
src = open(r'C:\Users\vishalt\Documents\NCS_MES\core\views.py', encoding='utf-8').read()
lines = src.splitlines()
for i, line in enumerate(lines):
    if 'COLUMN_MAP' in line:
        print(f'COLUMN_MAP at index {i+1}: {repr(line)}')
        break
