import urllib.parse, urllib.request
data = {
    'system_version':'R9',
    'age_group':'under70',
    'start_date':'2025-01-01',
    'drug_id':'dupixent_300',
    'income_category':'R9_370_510',
    'prescription_interval_weeks':'12',
    'use_subsidy':'on',
    'subsidy_cap':'20000',
    'use_medical_deduction':'on',
}
enc = urllib.parse.urlencode(data).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:5000/calculate', data=enc, method='POST')
with urllib.request.urlopen(req, timeout=30) as resp:
    html = resp.read().decode('utf-8')
    with open('tools/response_calc.html','w',encoding='utf-8') as f:
        f.write(html)
print('POST_OK len=', len(html))
