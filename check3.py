import ast
src = open(r'C:\Users\vishalt\Documents\NCS_MES\core\views.py', encoding='utf-8').read()
lines = src.splitlines()
total_ok = 0
for start in range(0, len(lines), 10):
    try:
        ast.parse('\n'.join(lines[start:start+10]))
        total_ok += 1
    except SyntaxError as e:
        print(f'FAIL at start {start}, chunk size 10: {e}')
        # Try to narrow down
        for end in range(start+2, min(start+11, len(lines)+1)):
            try:
                ast.parse('\n'.join(lines[start:end]))
            except SyntaxError as e2:
                print(f'  narrows to lines {start+1}-{end}: {e2}')
                break
        break
print(f'OK chunks so far: {total_ok}')
