import requests, time, sys
from datetime import date

base = 'http://127.0.0.1:5000'
post_url = base + '/calculate'
print_url = base + '/print'

payload = {
    'system_version': 'R9',
    'age_group': 'under70',
    'start_date': date.today().strftime('%Y-%m-%d'),
    'drug_id': '',
    'qty2': '1',
    'qty3': '1',
    'prescription_interval_weeks': '12',
    'burden_ratio': '0.3',
    'income_category': '',
}

print('POSTing to', post_url)
try:
    r = requests.post(post_url, data=payload, timeout=10)
    print('POST status:', r.status_code)
    print('Result-page contains result-section:', 'id="result-section"' in r.text)
    print("Result-page contains '/print' link:", '/print' in r.text)
except Exception as e:
    print('POST ERROR', repr(e))
    sys.exit(2)

# small pause to allow server-side state (if any)
time.sleep(0.5)

print('GET', print_url)
try:
    r2 = requests.get(print_url, timeout=10)
    print('GET /print status:', r2.status_code)
    print('Response snippet:')
    print(r2.text[:800])
except Exception as e:
    print('GET /print ERROR', repr(e))
    sys.exit(3)
