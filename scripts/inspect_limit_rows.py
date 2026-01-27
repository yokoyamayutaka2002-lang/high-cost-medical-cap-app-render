import csv
from pathlib import Path
p=Path(__file__).parents[1]/'data'/'limit_table.csv'
print('reading',p)
with p.open(encoding='utf-8') as f:
    reader=csv.DictReader(f)
    rows=[r for r in reader if r.get('system_version')=='R7' and r.get('age_group')=='under70']
    print('count',len(rows))
    for r in rows:
        print(repr((r.get('income_code'), r.get('income_label'))))
