import csv
from src.xolair import build_xolair_prescription, get_xolair_dose

print('=== build_xolair_prescription outputs ===')
for d in (150,225,300,375):
    pres = build_xolair_prescription(d)
    print(d, pres)

print('\n=== get_xolair_dose sample ===')
print('get_xolair_dose(350,65)=', get_xolair_dose(350,65))

# load data/drug_price.csv manually
price_rows = []
with open('data/drug_price.csv', encoding='utf-8') as f:
    r = csv.DictReader(f)
    for row in r:
        price_rows.append(row)

print('\nLoaded', len(price_rows),'drug_price rows')

price_by_id = {r['drug_id']: float(r['price_per_unit'] or 0) for r in price_rows}
price_by_name = {r['drug_name']: float(r['price_per_unit'] or 0) for r in price_rows}
print('sample ids:', list(price_by_id.keys())[:20])
print('sample names:', list(price_by_name.keys())[:20])

for d in (150,225,300,375):
    pres = build_xolair_prescription(d)
    gross_id = 0
    gross_name = 0
    for it in pres:
        # try lookups
        did = it.get('drug_id')
        dname = it.get('drug_name')
        qty = it.get('qty',0)
        p_id = price_by_id.get(did,0) if did else 0
        p_name = price_by_name.get(dname,0) if dname else 0
        gross_id += p_id * qty
        gross_name += p_name * qty
        print(f'  item: {it} p_id={p_id} p_name={p_name}')
    print(f'dose {d}: gross_id={gross_id} gross_name={gross_name}\n')
