import re
from pathlib import Path
p = Path('tools/response_calc.html')
if not p.exists():
    print('NO_RESPONSE_FILE')
    raise SystemExit(1)
html = p.read_text(encoding='utf-8')

# Extract the first prescription schedule table after '<h3>処方スケジュール'
m = re.search(r'<h3>処方スケジュール.*?<table.*?>(.*?)</table>', html, re.S)
if not m:
    print('NO_SCHEDULE_TABLE')
    raise SystemExit(2)
table_html = m.group(1)
# Find all rows in tbody
rows = re.findall(r'<tr>(.*?)</tr>', table_html, re.S)
if not rows:
    print('NO_SCHEDULE_ROWS')
    raise SystemExit(3)

bad_cells = []
import html as _html
for i, r in enumerate(rows, start=1):
    tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)
    if not tds:
        continue
    last = tds[-1].strip()
    # remove html tags inside cell (if any)
    last_text = re.sub(r'<[^>]+>', '', last).strip()
    last_text = _html.unescape(last_text)
    # Check for em-dash or other placeholder
    if last_text == '—' or not re.match(r'^¥[0-9,]+$', last_text):
        bad_cells.append((i, last_text))

# Check medical deduction fields
# Look for the block containing '医療費控除還付' and extract first following ¥ value
m2 = re.search(r'医療費控除還付.*?¥([0-9,]+)', html, re.S)
if m2:
    total_refund = int(m2.group(1).replace(',', ''))
else:
    total_refund = 0

m3 = re.search(r'所得税.*?¥([0-9,]+)', html, re.S)
if m3:
    income_refund = int(m3.group(1).replace(',', ''))
else:
    income_refund = 0

m4 = re.search(r'住民税.*?¥([0-9,]+)', html, re.S)
if m4:
    resident_refund = int(m4.group(1).replace(',', ''))
else:
    resident_refund = 0

# Results
ok_schedule = len(bad_cells) == 0
ok_medical = (income_refund != 0 or resident_refund != 0 or total_refund != 0)

print('SCHEDULE_OK' if ok_schedule else 'SCHEDULE_FAIL')
if not ok_schedule:
    for idx, v in bad_cells[:10]:
        print(f'ROW {idx}: {v}')

print('MEDICAL_OK' if ok_medical else 'MEDICAL_FAIL')
print('medical_totals:', {'total_refund': total_refund, 'income': income_refund, 'resident': resident_refund})

if not ok_schedule or not ok_medical:
    # dump snippet around '付加給付調整後' header to help debug
    mm = re.search(r'付加給付調整後[\s\S]{0,2000}', html)
    if mm:
        snippet = mm.group(0)
        fn = Path('tools/debug_snippet.html')
        fn.write_text(snippet, encoding='utf-8')
        print('WROTE debug_snippet.html')
    # Also write full response for inspection
    Path('tools/response_full.html').write_text(html, encoding='utf-8')
    print('WROTE tools/response_full.html')

if ok_schedule and ok_medical:
    print('ALL_PASS')
else:
    print('SOME_FAIL')
