import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from webapp.app import app
from datetime import date

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

with app.test_client() as c:
    print('Posting to /calculate via test_client')
    r = c.post('/calculate', data=payload)
    print('POST status:', r.status_code)
    print('Result contains result-section:', b'id="result-section"' in r.data)
    print("Result contains /print link:", b'/print' in r.data)

    print('\nRequesting /print via test_client')
    r2 = c.get('/print')
    print('GET /print status:', r2.status_code)
    print('GET /print data snippet:\n', r2.data[:800].decode('utf-8', errors='replace'))
