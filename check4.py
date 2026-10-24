import ast
src = open(r'C:\Users\vishalt\Documents\NCS_MES\core\views.py', encoding='utf-8').read()
lines = src.splitlines()
with open(r'C:\Users\vishalt\Documents\NCS_MES\badregion.txt', 'w', encoding='utf-8') as f:
    for i in range(3060, 3116):
        f.write(f'{i+1}: {repr(lines[i])}\n')
