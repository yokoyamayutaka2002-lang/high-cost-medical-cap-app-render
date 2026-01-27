import csv
from collections import defaultdict
from pathlib import Path

p = Path(__file__).parent.parent / 'data' / 'income_category_master.csv'
if not p.exists():
    raise SystemExit(f"File not found: {p}")

rows = list(csv.DictReader(p.open(encoding='utf-8')))

# Count by system_base x age_group
counts = defaultdict(int)
entries = defaultdict(list)
for r in rows:
    key = (r['system_base'], r['age_group'])
    counts[key] += 1
    entries[key].append((r['income_code'], r['display_name']))

print('Counts per system_base x age_group:')
for key in sorted(counts.keys()):
    print(f" - {key[0]} / {key[1]}: {counts[key]}")

print('\nEntries:')
for key in sorted(entries.keys()):
    print(f"\n== {key[0]} / {key[1]} ==")
    for code, name in entries[key]:
        print(f"  {code} : {name}")
