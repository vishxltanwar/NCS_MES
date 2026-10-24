import ast
src = open(r'C:\Users\vishalt\Documents\NCS_MES\core\views.py', encoding='utf-8').read()
lines = src.splitlines()
for i in range(3095, 3116):
    print(f'{i+1}: {repr(lines[i][:75])}')
