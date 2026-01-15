import csv, json
from collections import OrderedDict

mapping = OrderedDict()
with open('data/limit_table.csv', encoding='utf-8') as f:
    reader = csv.reader(f)
    for row in reader:
        if not row: continue
        if row[0].strip().startswith('#'): continue
        if len(row) < 2: continue
        # ensure 10 columns by padding
        row = row + ['']*(10-len(row))
        sv, code, label, age = row[0], row[1], row[2], row[3]
        if sv not in mapping: mapping[sv] = OrderedDict()
        if age not in mapping[sv]: mapping[sv][age] = []
        mapping[sv][age].append([code, label])

print(json.dumps(mapping, ensure_ascii=False, indent=2))
