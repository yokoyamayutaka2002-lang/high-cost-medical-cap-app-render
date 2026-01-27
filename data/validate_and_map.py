import csv, json

bad = []
with open('data/limit_table.csv', encoding='utf-8') as f:
    for i, row in enumerate(csv.reader(f)):
        if len(row) == 0:
            continue
        if row[0].strip().startswith('#'):
            continue
        if len(row) != 10:
            bad.append({'line': i+1, 'cols': len(row), 'row': row})

print('BAD =', json.dumps(bad, ensure_ascii=False, indent=2))

print('\nSample mapping output:')
from webapp.app import build_income_map
print(json.dumps(build_income_map(), ensure_ascii=False, indent=2))
