import re, os

names = set()
files = []
for root, dirs, fs in os.walk('san_xuat'):
    if '__pycache__' in root:
        continue
    for f in fs:
        if f.endswith(('.html', '.py')):
            files.append(os.path.join(root, f))

for fp in files:
    try:
        text = open(fp, encoding='utf-8').read()
    except Exception:
        continue
    for m in re.finditer(r'san_xuat:([a-zA-Z0-9_]+)', text):
        names.add(m.group(1))

for n in sorted(names):
    print(n)
print('TOTAL', len(names))
